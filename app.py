
import base64, io, json, os, sqlite3, statistics
from datetime import datetime
from pathlib import Path
import pandas as pd
import streamlit as st
from openai import OpenAI

DB = Path("products.db")
conn = sqlite3.connect(DB, check_same_thread=False)
conn.execute("""CREATE TABLE IF NOT EXISTS products (
 id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, brand TEXT, product TEXT,
 model TEXT, sku TEXT, category TEXT, size TEXT, color TEXT, condition TEXT,
 asking REAL, value REAL, low REAL, high REAL, listing REAL, fees REAL,
 profit REAL, roi REAL, confidence REAL, decision TEXT, notes TEXT)""")
conn.commit()

st.set_page_config(page_title="Product Price AI V2", page_icon="📦", layout="wide")
st.title("📦 Product Price AI V2")
st.caption("Kuvasta tuotteeksi → vertailuhinnat → arvo → jälleenmyyntipäätös → Excel")

with st.sidebar:
    st.header("Asetukset")
    key = st.text_input("OPENAI_API_KEY", value=os.getenv("OPENAI_API_KEY",""), type="password")
    model = st.text_input("Mallin nimi", value="gpt-5.6-luna")
    default_fees = st.number_input("Oletuskulut (€)", 0.0, 1000.0, 10.0, 1.0)
    st.divider()
    st.write("Vihreä = hyvä marginaali, keltainen = rajatapaus, punainen = heikko.")

if not key:
    st.warning("Syötä API-avain vasemmalle.")
    st.stop()
client = OpenAI(api_key=key)

tab1, tab2 = st.tabs(["➕ Arvioi tuote", "📊 Portfolio"])

with tab1:
    files = st.file_uploader("Tuotekuvat (1–5)", type=["jpg","jpeg","png","webp"], accept_multiple_files=True)
    asking = st.number_input("Ostohinta / pyyntihinta (€)", 0.0, 100000.0, 0.0, 1.0)
    fees = st.number_input("Arvioidut kulut (€)", 0.0, 10000.0, float(default_fees), 1.0)
    extra = st.text_area("Lisätieto", placeholder="Esim. koko 110, käytetty kerran, Vantaa")
    if st.button("🔎 Arvioi", type="primary", disabled=not files):
        def data_url(f):
            b=f.read(); return f"data:{f.type or 'image/jpeg'};base64,{base64.b64encode(b).decode()}"
        content=[{"type":"input_text","text":"""Tunnista tuote erittäin tarkasti kuvista. Käytä näkyvää tekstiä,
etikettejä, logoja, mallinumeroita ja yksityiskohtia. Älä keksi tietoja. Arvioi kunto vain näkyvien
merkkien perusteella. Palauta JSON:
{"brand":"","product_name":"","model":"","sku":"","category":"","size":"","color":"",
"condition":"","condition_notes":"","identification_confidence":0.0,"search_query":""}""" +
                  "\nKäyttäjän lisätieto: "+extra}]
        for f in files: content.append({"type":"input_image","image_url":data_url(f)})
        with st.spinner("Tunnistetaan…"):
            rr=client.responses.create(model=model,input=[{"role":"user","content":content}],
                                       text={"format":{"type":"json_object"}})
        p=json.loads(rr.output_text)
        st.subheader("Tunnistus")
        st.json(p)

        prompt=f"""Arvioi tämän tuotteen jälleenmyyntiarvo Suomessa/Euroopassa.
Tuote: {json.dumps(p,ensure_ascii=False)}
Etsi verkosta mahdollisimman monta relevanttia vertailua. Priorisoi sama SKU/malli, sitten sama
tuote eri koossa, sitten erittäin läheiset verrokit. Erota pyyntihinnat ja toteutuneet myynnit.
Älä keksi hintoja, lähteitä tai toteutuneita myyntejä. Huomioi kunto, koko ja mahdolliset erot.
Palauta JSON:
{{"comparables":[{{"source":"","url":"","title":"","price_eur":0,"sale_type":"asking_or_sold",
"condition":"","size":"","match_quality":0.0}}],"estimated_value_eur":0,"low_eur":0,"high_eur":0,
"recommended_listing_eur":0,"confidence":0.0,"method_notes":""}}"""
        with st.spinner("Tutkitaan markkinahintoja…"):
            rr=client.responses.create(model=model,tools=[{"type":"web_search_preview"}],input=prompt)
        try: v=json.loads(rr.output_text)
        except:
            st.error("Hintatuloksen JSON epäonnistui."); st.code(rr.output_text); st.stop()

        est=float(v.get("estimated_value_eur") or 0); low=float(v.get("low_eur") or 0)
        high=float(v.get("high_eur") or 0); listing=float(v.get("recommended_listing_eur") or est)
        profit=listing-asking-fees
        roi=(profit/asking*100) if asking>0 else None
        # Decision thresholds: require both positive profit and margin; confidence tempers borderline cases.
        if asking<=0: decision="⚪ EI OSTOHINTAA"
        elif profit>=asking*0.75 and roi>=75: decision="🟢 OSTA"
        elif profit>=asking*0.35 and roi>=35: decision="🟡 HARKITSE"
        else: decision="🔴 ÄLÄ OSTA"

        a,b,c,d,e=st.columns(5)
        a.metric("Arvo",f"{est:.0f} €")
        b.metric("Arvioalue",f"{low:.0f}–{high:.0f} €")
        c.metric("Myyntihinta",f"{listing:.0f} €")
        d.metric("Voitto",f"{profit:.0f} €" if asking else "—")
        e.metric("ROI",f"{roi:.0f} %" if roi is not None else "—")
        st.subheader(decision)
        st.write("Luottamus:",f"{float(v.get('confidence',0))*100:.0f} %")
        st.write(v.get("method_notes",""))
        if v.get("comparables"): st.dataframe(pd.DataFrame(v["comparables"]),use_container_width=True)

        row=(datetime.now().isoformat(timespec="seconds"),p.get("brand",""),p.get("product_name",""),
             p.get("model",""),p.get("sku",""),p.get("category",""),p.get("size",""),p.get("color",""),
             p.get("condition",""),asking,est,low,high,listing,fees,profit if asking else None,
             roi,float(v.get("confidence",0))*100,decision,v.get("method_notes",""))
        conn.execute("""INSERT INTO products(created_at,brand,product,model,sku,category,size,color,condition,
        asking,value,low,high,listing,fees,profit,roi,confidence,decision,notes)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",row); conn.commit()

        export=pd.DataFrame([{
            "Aikaleima":row[0],"Brändi":row[1],"Tuote":row[2],"Malli":row[3],"SKU":row[4],
            "Kategoria":row[5],"Koko":row[6],"Väri":row[7],"Kunto":row[8],"Ostohinta €":asking,
            "Arvio €":est,"Alaraja €":low,"Yläraja €":high,"Suositeltu myyntihinta €":listing,
            "Kulut €":fees,"Voitto €":profit if asking else None,"ROI %":roi,
            "Luottamus %":float(v.get("confidence",0))*100,"Päätös":decision
        }])
        buf=io.BytesIO()
        with pd.ExcelWriter(buf,engine="openpyxl") as w:
            export.to_excel(w,index=False,sheet_name="Arvio")
            if v.get("comparables"): pd.DataFrame(v["comparables"]).to_excel(w,index=False,sheet_name="Vertailut")
        st.download_button("📊 Lataa tämän tuotteen Excel",buf.getvalue(),
                           "product-price-estimate.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

with tab2:
    df=pd.read_sql_query("SELECT * FROM products ORDER BY id DESC",conn)
    if df.empty:
        st.info("Portfolio on vielä tyhjä.")
    else:
        total_value=df["value"].sum()
        total_profit=df["profit"].fillna(0).sum()
        avg_roi=df["roi"].dropna().mean() if df["roi"].notna().any() else 0
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Tuotteita",len(df)); c2.metric("Arvioitu arvo",f"{total_value:.0f} €")
        c3.metric("Arvioitu voitto",f"{total_profit:.0f} €"); c4.metric("Keskimääräinen ROI",f"{avg_roi:.0f} %")
        st.subheader("Päätökset")
        st.bar_chart(df["decision"].value_counts())
        st.dataframe(df[["id","created_at","brand","product","asking","value","listing","profit","roi","confidence","decision"]],
                     use_container_width=True)
        buf=io.BytesIO()
        with pd.ExcelWriter(buf,engine="openpyxl") as w:
            df.to_excel(w,index=False,sheet_name="Portfolio")
        st.download_button("📥 Vie koko portfolio Exceliin",buf.getvalue(),"product-price-portfolio.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        if st.button("Tyhjennä portfolio"):
            conn.execute("DELETE FROM products"); conn.commit(); st.rerun()
