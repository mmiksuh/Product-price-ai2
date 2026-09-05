import base64, io, json, os, sqlite3, statistics, re
from datetime import datetime
from pathlib import Path
import pandas as pd
import streamlit as st
from openai import OpenAI

DB = Path('products.db')
conn = sqlite3.connect(DB, check_same_thread=False)
conn.execute('''CREATE TABLE IF NOT EXISTS products (
 id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, brand TEXT, product TEXT,
 model TEXT, sku TEXT, category TEXT, size TEXT, color TEXT, condition TEXT,
 asking REAL, value REAL, low REAL, high REAL, listing REAL, fees REAL,
 profit REAL, roi REAL, confidence REAL, decision TEXT, risk TEXT, sell_time TEXT,
 max_buy REAL, notes TEXT)''')
conn.commit()

st.set_page_config(page_title='Product Price AI V3', page_icon='📦', layout='wide')
st.title('📦 Product Price AI V3')
st.caption('Kuvat + tuotetunnistus + visuaalinen vertailu + markkinahaku + jälleenmyyntipäätös')

with st.sidebar:
    st.header('Asetukset')
    api_key = st.secrets.get('OPENAI_API_KEY', os.getenv('OPENAI_API_KEY', ''))
    model = st.text_input('Mallin nimi', value=os.getenv('OPENAI_MODEL', 'gpt-5.6-luna'))
    default_fees = st.number_input('Oletuskulut (€)', 0.0, 1000.0, 10.0, 1.0)
    target_profit = st.number_input('Tavoitevoitto (€)', 0.0, 10000.0, 25.0, 1.0)
    if not api_key:
        st.warning('OPENAI_API_KEY puuttuu Streamlit Secrets -asetuksista.')

if not api_key:
    st.info('Lisää OPENAI_API_KEY Streamlitin Secrets-kohtaan, jotta arviointi voidaan tehdä.')
    st.stop()
client = OpenAI(api_key=api_key)

def data_url(f):
    b = f.read()
    return f'data:{f.type or "image/jpeg"};base64,{base64.b64encode(b).decode()}'

def safe_json(text):
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r'\{.*\}', text, re.S)
        if m:
            return json.loads(m.group(0))
        raise

def pct(x):
    try: return f'{float(x)*100:.0f} %'
    except: return '—'

tab1, tab2 = st.tabs(['➕ Arvioi tuote', '📊 Portfolio'])

with tab1:
    files = st.file_uploader('Tuotekuvat (1–5)', type=['jpg','jpeg','png','webp'], accept_multiple_files=True)
    asking = st.number_input('Ostohinta / pyyntihinta (€)', 0.0, 100000.0, 0.0, 1.0)
    fees = st.number_input('Arvioidut kulut (€)', 0.0, 10000.0, float(default_fees), 1.0)
    extra = st.text_area('Lisätieto', placeholder='Esim. koko 110, käytetty kerran, Helsinki, laput mukana')

    if st.button('🔎 Tunnista, vertaile ja arvioi', type='primary', disabled=not files):
        if len(files) > 5:
            st.error('Lataa enintään 5 kuvaa.')
            st.stop()

        content = [{"type":"input_text", "text": '''Analysoi KAIKKI annetut tuotekuvat yhdessä. Tavoite on tunnistaa mahdollisimman tarkasti juuri kuvissa oleva yksittäinen tuote, ei vain tuoteryhmää.

Käytä visuaalisia yksityiskohtia: muoto, leikkaukset, logot, värit, materiaalit, ompeleet, pohjat, napit, vetoketjut, tarrat, etiketit, mallinumerot, SKU:t, sarjanumerot ja pakkaukset. Lue kuvissa näkyvä teksti. Arvioi kunto vain näkyvien asioiden perusteella. Jos tieto ei ole varma, merkitse epävarmaksi äläkä keksi.

Palauta vain JSON:
{"brand":"","product_name":"","model":"","sku":"","category":"","size":"","color":"","condition":"","condition_notes":"","visual_fingerprint":"","identification_confidence":0.0,"possible_variants":[],"search_queries":[]}

Käyttäjän lisätieto: ''' + extra}]
        for f in files:
            content.append({"type":"input_image", "image_url": data_url(f)})

        with st.spinner('🔬 Analysoidaan kuvia ja tunnistetaan tarkka malli…'):
            r = client.responses.create(model=model, input=[{"role":"user","content":content}],
                text={"format":{"type":"json_object"}})
        product = safe_json(r.output_text)

        st.subheader('🔍 Tunnistus')
        cols = st.columns(4)
        cols[0].metric('Brändi', product.get('brand') or '—')
        cols[1].metric('Malli', product.get('model') or product.get('product_name') or '—')
        cols[2].metric('SKU', product.get('sku') or '—')
        cols[3].metric('Tunnistus', pct(product.get('identification_confidence',0)))
        with st.expander('Näytä tarkka kuva-analyysi'):
            st.json(product)

        search_prompt = f'''Toimi jälleenmyyntimarkkinan tutkijana. Arvioit tuotetta Suomessa/Euroopassa.

TUOTTEEN KUVA-ANALYYSI:
{json.dumps(product, ensure_ascii=False)}

Etsi verkosta oikeita ja mahdollisimman tuoreita vertailuja. Käytä ensisijaisesti täsmälleen samaa SKU:ta/mallinumeroa ja samaa tuotetta. Jos sitä ei löydy riittävästi, käytä samaa tarkkaa mallia eri koossa/värissä ja vasta sen jälkeen erittäin läheisiä verrokkeja. Tarkista että löydetty tuote vastaa kuvauksen ja visuaalisen tunnisteen perusteella mahdollisimman hyvin.

Erota pyyntihinnat ja toteutuneet myynnit. Älä keksi hintoja, myyntejä tai URL-osoitteita. Jos toteutuneita myyntejä ei löydy, sano se selvästi. Huomioi koko, väri, kunto ja sesonki. Arvioi myös todennäköinen myyntiaika.

Palauta vain JSON seuraavalla rakenteella:
{{"comparables":[{{"source":"","url":"","title":"","price_eur":0,"sale_type":"asking|sold","condition":"","size":"","match_quality":0.0,"visual_match_reason":""}}],"estimated_value_eur":0,"low_eur":0,"high_eur":0,"recommended_listing_eur":0,"confidence":0.0,"sell_time_min_days":0,"sell_time_max_days":0,"market_demand":"low|medium|high","counterfeit_risk":"low|medium|high|unknown","max_buy_price_eur":0,"method_notes":"","data_quality":"poor|fair|good|excellent"}}

Maksimihintaostolle lasketaan niin, että ostohinnan + kulujen jälkeen tavoitteena on vähintään käyttäjän ilmoittama tavoitevoitto {target_profit:.2f} euroa. Jos markkinadata on heikkoa, laske varovaisemmin ja pienennä luottamusta.'''

        with st.spinner('🌐 Haetaan verkosta vertailutuotteita ja tarkistetaan markkinahintoja…'):
            try:
                rr = client.responses.create(model=model, tools=[{"type":"web_search_preview"}], input=search_prompt)
                valuation = safe_json(rr.output_text)
            except Exception as e:
                st.error(f'Verkkohaku epäonnistui: {e}')
                st.stop()

        est = float(valuation.get('estimated_value_eur') or 0)
        low = float(valuation.get('low_eur') or 0)
        high = float(valuation.get('high_eur') or 0)
        listing = float(valuation.get('recommended_listing_eur') or est)
        max_buy = float(valuation.get('max_buy_price_eur') or max(0, listing - fees - target_profit))
        profit = listing - asking - fees
        roi = (profit / asking * 100) if asking > 0 else None
        conf = float(valuation.get('confidence') or 0) * 100
        if asking <= 0:
            decision = '⚪ SYÖTÄ OSTOHINTA'
        elif max_buy >= asking and conf >= 60:
            decision = '🟢 OSTA'
        elif max_buy >= asking * 0.85:
            decision = '🟡 HARKITSE'
        else:
            decision = '🔴 ÄLÄ OSTA'

        st.subheader('💰 Jälleenmyyntiarvio')
        a,b,c,d,e,f = st.columns(6)
        a.metric('Arvo', f'{est:.0f} €')
        b.metric('Arvioalue', f'{low:.0f}–{high:.0f} €')
        c.metric('Suositeltu pyynti', f'{listing:.0f} €')
        d.metric('Maksimihinta', f'{max_buy:.0f} €')
        e.metric('Myyntiaika', f"{valuation.get('sell_time_min_days','?')}–{valuation.get('sell_time_max_days','?')} pv")
        f.metric('Luottamus', f'{conf:.0f} %')
        st.subheader(decision)
        st.write(f"**Markkinakysyntä:** {valuation.get('market_demand','—')}  |  **Väärennösriski:** {valuation.get('counterfeit_risk','—')}  |  **Datalaatu:** {valuation.get('data_quality','—')}")
        st.write(valuation.get('method_notes',''))

        if asking > 0:
            x,y,z = st.columns(3)
            x.metric('Arvioitu voitto', f'{profit:.0f} €')
            y.metric('ROI', f'{roi:.0f} %' if roi is not None else '—')
            z.metric('Tavoitevoitto', f'{target_profit:.0f} €')

        comps = valuation.get('comparables') or []
        if comps:
            st.subheader('🖼️ + 🔎 Vertailut')
            st.dataframe(pd.DataFrame(comps), use_container_width=True)

        with st.expander('✍️ Valmis myynti-ilmoituksen pohja'):
            listing_prompt = f'''Kirjoita suomeksi lyhyt mutta myyvä jälleenmyynti-ilmoitus tästä tuotteesta. Älä keksi puuttuvia tietoja. Tuotetiedot: {json.dumps(product, ensure_ascii=False)}. Tee otsikko, kuvaus, tärkeät tiedot ja suositeltu hinta {listing:.0f} €.''' 
            try:
                lr = client.responses.create(model=model, input=listing_prompt)
                st.write(lr.output_text)
            except Exception:
                st.info('Ilmoitustekstin luonti ei onnistunut tällä kertaa.')

        row=(datetime.now().isoformat(timespec='seconds'),product.get('brand',''),product.get('product_name',''),
             product.get('model',''),product.get('sku',''),product.get('category',''),product.get('size',''),product.get('color',''),
             product.get('condition',''),asking,est,low,high,listing,fees,profit if asking else None,roi,conf,decision,
             valuation.get('counterfeit_risk','unknown'),f"{valuation.get('sell_time_min_days','?')}-{valuation.get('sell_time_max_days','?')} pv",
             max_buy,valuation.get('method_notes',''))
        conn.execute('''INSERT INTO products(created_at,brand,product,model,sku,category,size,color,condition,asking,value,low,high,listing,fees,profit,roi,confidence,decision,risk,sell_time,max_buy,notes)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', row)
        conn.commit()

        export = pd.DataFrame([{
            'Aikaleima':row[0],'Brändi':row[1],'Tuote':row[2],'Malli':row[3],'SKU':row[4],'Kategoria':row[5],
            'Koko':row[6],'Väri':row[7],'Kunto':row[8],'Ostohinta €':asking,'Arvio €':est,'Alaraja €':low,'Yläraja €':high,
            'Suositeltu myyntihinta €':listing,'Maksimihinta ostolle €':max_buy,'Kulut €':fees,'Voitto €':profit if asking else None,
            'ROI %':roi,'Luottamus %':conf,'Päätös':decision,'Väärennösriski':valuation.get('counterfeit_risk','unknown'),
            'Myyntiaika':f"{valuation.get('sell_time_min_days','?')}-{valuation.get('sell_time_max_days','?')} pv"
        }])
        buf=io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as w:
            export.to_excel(w,index=False,sheet_name='Arvio')
            if comps: pd.DataFrame(comps).to_excel(w,index=False,sheet_name='Vertailut')
        st.download_button('📊 Lataa Excel',buf.getvalue(),'product-price-estimate-v3.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

with tab2:
    df=pd.read_sql_query('SELECT * FROM products ORDER BY id DESC',conn)
    if df.empty:
        st.info('Portfolio on vielä tyhjä.')
    else:
        c1,c2,c3,c4=st.columns(4)
        c1.metric('Tuotteita',len(df)); c2.metric('Arvioitu arvo',f"{df.value.sum():.0f} €")
        c3.metric('Arvioitu voitto',f"{df.profit.fillna(0).sum():.0f} €")
        c4.metric('Keskimääräinen ROI',f"{df.roi.dropna().mean():.0f} %" if df.roi.notna().any() else '—')
        st.dataframe(df[['id','created_at','brand','product','model','asking','value','listing','max_buy','profit','roi','confidence','decision','risk','sell_time']],use_container_width=True)
        buf=io.BytesIO()
        with pd.ExcelWriter(buf,engine='openpyxl') as w: df.to_excel(w,index=False,sheet_name='Portfolio')
        st.download_button('📥 Vie portfolio Exceliin',buf.getvalue(),'product-price-portfolio-v3.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        if st.button('Tyhjennä portfolio'):
            conn.execute('DELETE FROM products'); conn.commit(); st.rerun()
