import streamlit as st
from supabase import create_client
import ast
from fpdf import FPDF
import os
import requests

# --- CONFIGURAZIONE PWA PER SCHERMATA HOME ---
st.markdown("""
    <link rel="manifest" href="data:application/manifest+json,{
        'name': 'SlotGarage',
        'short_name': 'SlotGarage',
        'start_url': '/',
        'display': 'standalone',
        'background_color': '#ffffff',
        'theme_color': '#000000',
        'icons': [
            {
                'src': 'https://raw.githubusercontent.com/garganoslotcar-max/SlotGarage/main/logo.png',
                'sizes': '512x512',
                'type': 'image/png'
            }
        ]
    }">
""", unsafe_allow_html=True)

# --- CONFIGURAZIONE SUPABASE ---
SUPABASE_URL = "https://rmfaphfksvcyynfrrbsy.supabase.co"
SUPABASE_KEY = "sb_publishable_vp-3OcwsKymyHEgP8XlbsQ_KVFQh0I6"

@st.cache_resource
def init_connection():
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        return None

supabase = init_connection()

LOGO_PATH = "logo.png" 

st.set_page_config(page_title="SlotGarage", page_icon=LOGO_PATH, layout="wide")

# --- INTESTAZIONE CON LOGO E SCRITTA INGRANDITA E ABBASSATA ---
col_logo, col_titolo = st.columns([2, 10])
with col_logo:
    try:
        st.image(LOGO_PATH, width=220)
    except Exception:
        st.write("🏎️")
with col_titolo:
    st.markdown("<h1 style='margin-top: 25px; font-size: 4.2rem;'>SlotGarage</h1>", unsafe_allow_html=True)

if not supabase:
    st.error("Errore di connessione a Supabase.")
    st.stop()

# --- CARICAMENTO DATI RESILIENTE ---
@st.cache_data(ttl=5)
def get_data(table_name):
    if not supabase:
        return []
    try:
        response = supabase.table(table_name).select("*").execute()
        return response.data if response.data else []
    except Exception:
        return []

produttori = get_data("Produttori")
categorie = get_data("Categorie")
modelli = get_data("MODELLI")
catalogo_componenti = get_data("CatalogoComponenti")

if not produttori and not modelli:
    st.warning("Connessione al cloud in corso o database temporaneamente in standby...")
    if st.button("🔄 Riprova Connessione"):
        st.cache_data.clear()
        st.rerun()

# --- INIZIALIZZAZIONE STATO PER MODIFICA E NAVIGAZIONE ---
if "modifying_config_id" not in st.session_state:
    st.session_state.modifying_config_id = None
if "modifying_data" not in st.session_state:
    st.session_state.modifying_data = None
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "📋 Visualizza Modelli"

# --- SEZIONE FILTRI E SELEZIONE ---
st.header("🔍 Navigazione e Filtri")
col_f1, col_f2, col_f3 = st.columns(3)

prod_options = {p.get("name"): p.get("id") for p in produttori if p.get("name") and p.get("id")}
with col_f1:
    selected_prod_name = st.selectbox("Seleziona Produttore", ["Tutti"] + list(prod_options.keys()))

if selected_prod_name != "Tutti":
    prod_id = prod_options[selected_prod_name]
    cat_options = {c.get("name"): c.get("id") for c in categorie if c.get("brand_it") == prod_id}
else:
    cat_options = {c.get("name"): c.get("id") for c in categorie if c.get("name") and c.get("id")}

with col_f2:
    selected_cat_name = st.selectbox("Seleziona Categoria", ["Tutte"] + list(cat_options.keys()))

if selected_cat_name != "Tutte":
    cat_id = cat_options[selected_cat_name]
    mod_list = [m.get("name") for m in modelli if m.get("category_id") == cat_id and m.get("name")]
else:
    mod_list = [m.get("name") for m in modelli if m.get("name")]

with col_f3:
    selected_model_name = st.selectbox("Seleziona Modello", ["Tutti"] + mod_list)

st.divider()

# --- MENU DI NAVIGAZIONE GESTITO VIA STATO (PER IL SALTO AUTOMATICO) ---
tabs_list = ["📋 Visualizza Modelli", "➕ Carica Modello", "🚗 Il Mio Garage"]
selected_tab = st.radio("Navigazione", tabs_list, index=tabs_list.index(st.session_state.active_tab) if st.session_state.active_tab in tabs_list else 0, horizontal=True, label_visibility="collapsed")
st.session_state.active_tab = selected_tab
st.divider()

def find_default_index(opzioni, model_name):
    if not model_name or model_name == "Tutti":
        return 0
    model_lower = model_name.lower()
    for idx, opt in enumerate(opzioni):
        if model_lower in opt.lower():
            return idx
    words = [w for w in model_lower.split() if len(w) > 2]
    for idx, opt in enumerate(opzioni):
        opt_lower = opt.lower()
        if any(w in opt_lower for w in words):
            return idx
    return 0

# --- FUNZIONE GENERAZIONE PDF ORIZZONTALE (LANDSCAPE) A PAGINA UNICA ---
def generate_pdf(config_name, modello_nome, dettagli, foto_url=None):
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    
    bg_dark = (30, 32, 36)
    accent_bar = (220, 50, 50)  
    text_dark = (40, 40, 40)
    text_light = (255, 255, 255)
    
    pdf.set_fill_color(250, 252, 255)
    pdf.rect(0, 0, 297, 210, 'F')
    
    # Top Banner con dicitura allineata a destra
    pdf.set_fill_color(*bg_dark)
    pdf.rect(0, 0, 297, 16, 'F')
    pdf.set_fill_color(*accent_bar)
    pdf.rect(0, 16, 297, 2, 'F')
    
    pdf.set_text_color(*text_light)
    pdf.set_font("Helvetica", 'B', 10)
    
    # Titolo a sinistra
    pdf.set_xy(10, 4.5)
    pdf.cell(150, 7, f"SLOTGARAGE  |  SCHEDA: {config_name.upper()}", ln=0)
    
    # Firma/Brand allineati a destra
    pdf.set_font("Helvetica", 'I', 9)
    pdf.set_xy(140, 4.5)
    pdf.cell(147, 7, "Generato con Slotgarage di Palena Emanuele", ln=1, align="R")
    
    left_x = 10
    left_w = 85
    current_y = 22
    
    # 1. Nome del Modello posizionato SOPRA l'immagine per evitare qualsiasi accavallamento
    pdf.set_text_color(*text_dark)
    pdf.set_font("Helvetica", 'B', 10)
    pdf.set_xy(left_x, current_y)
    pdf.cell(left_w, 6, f"Modello: {modello_nome}", ln=True)
    current_y += 7

    # 2. Immagine della vettura
    if foto_url:
        try:
            response_img = requests.get(foto_url, timeout=3)
            if response_img.status_code == 200:
                img_tmp_path = "temp_car_img.jpg"
                with open(img_tmp_path, "wb") as handler:
                    handler.write(response_img.content)
                pdf.image(img_tmp_path, x=left_x + 2, y=current_y, w=left_w - 4)
                current_y += 48  # Spazio riservato all'altezza dell'immagine
                if os.path.exists(img_tmp_path):
                    os.remove(img_tmp_path)
        except Exception: 
            pass

    current_y += 4

    col_w = 93
    col1_x = 98
    col2_x = 194
    
    pesi_motore_Keys = ["Peso_Carrozzeria", "Peso_Totale", "Giri_Motore", "Motore", "Supporto Motore", "Corona", "Pignoni"]
    
    # Filtraggio e pulizia dei dati specifici per il PDF (esclusi note, distanziali ant/post e gestione distanziale pickup con misura)
    dettagli_filtrati = {}
    for k, v in dettagli.items():
        if k.lower() == "note":
            continue
        if k in ["Distanziali_Anteriori", "Distanziali_Posteriori"]:
            continue
        if k == "Distanziali_Pickup":
            val_misura = dettagli.get("Distanziale_Pickup", "")
            if str(v).lower() == "sì" and val_misura and str(val_misura).lower() != "nessun distanziale disponibile":
                dettagli_filtrati["Distanziale_Pickup"] = val_misura
            else:
                dettagli_filtrati["Distanziale_Pickup"] = v
            continue
        if k == "Distanziale_Pickup":
            continue
        dettagli_filtrati[k] = v

    left_items = {k: v for k, v in dettagli_filtrati.items() if any(pk in k for pk in pesi_motore_Keys)}
    right_items = {k: v for k, v in dettagli_filtrati.items() if k not in left_items}

    def draw_tech_section(x, y, w, title, items_dict):
        pdf.set_fill_color(*bg_dark)
        pdf.set_text_color(*text_light)
        pdf.set_font("Helvetica", 'B', 9)
        pdf.set_xy(x, y)
        pdf.cell(w, 6, f"   {title}", ln=True, fill=True)
        
        item_y = y + 7.5
        for k, v in items_dict.items():
            pdf.set_text_color(*text_dark)
            pdf.set_font("Helvetica", '', 8.5)
            k_clean = str(k).replace("_", " ")
            v_clean = str(v)
            
            pdf.set_xy(x + 3, item_y)
            pdf.cell(34, 4.8, f"{k_clean}:", 0, 0)
            
            pdf.set_font("Helvetica", 'B', 8.5)
            pdf.set_xy(x + 37, item_y)
            
            start_val_y = pdf.get_y()
            pdf.multi_cell(w - 40, 4.2, f"{v_clean}")
            end_val_y = pdf.get_y()
            
            row_height = max(4.8, (end_val_y - start_val_y))
            item_y += row_height + 0.8

        return item_y - y

    box_start_y = 24
    h_col1 = draw_tech_section(col1_x, box_start_y, col_w, "PROPULSIONE & PESI", left_items if left_items else {"Info": "Nessun dato"})
    h_col2 = draw_tech_section(col2_x, box_start_y, col_w, "Assetto", right_items if right_items else dettagli_filtrati)

    max_box_h = max(h_col1, h_col2)
    next_y = box_start_y + max_box_h + 4

    note_val = dettagli.get("Note", "")
    if note_val and str(note_val).strip() != "":
        pdf.set_fill_color(*bg_dark)
        pdf.set_text_color(*text_light)
        pdf.set_font("Helvetica", 'B', 8.5)
        pdf.set_xy(col1_x, next_y)
        pdf.cell(189, 5, "   NOTE DI SETTING / COLLAUDO", ln=True, fill=True)
        
        pdf.set_text_color(*text_dark)
        pdf.set_font("Helvetica", '', 8.5)
        pdf.set_xy(col1_x + 3, next_y + 5.5)
        pdf.multi_cell(183, 4, str(note_val))

    return pdf.output(dest='S').encode('latin-1', 'replace')

# --- GESTIONE SEZIONI (TAB) ---

if st.session_state.active_tab == "📋 Visualizza Modelli":
    if selected_model_name != "Tutti":
        modello_selezionato = next((m for m in modelli if m.get("name") == selected_model_name), None)
        modello_id = modello_selezionato.get("id") if modello_selezionato else None
        category_id = cat_options.get(selected_cat_name) if selected_cat_name in cat_options else None
        prod_id_selezionato = prod_options.get(selected_prod_name) if selected_prod_name in prod_options else None

        edit_data = st.session_state.modifying_data if st.session_state.modifying_config_id else {}

        if st.session_state.modifying_config_id:
            st.info(f"Stai modificando una configurazione esistente. Clicca su 'Salva Modifiche' per confermare.")

        st.subheader(f"Configurazione: {selected_model_name}")
        
        if modello_selezionato and modello_selezionato.get("foto_url"):
            try:
                st.image(modello_selezionato.get("foto_url"), caption=selected_model_name, width=250)
            except Exception:
                st.warning("Impossibile caricare l'immagine dal link fornito.")
        
        if selected_prod_name != "Tutti":
            st.write(f"### ⚙️ Setup Avanzato - {selected_prod_name}")
            
            pezzi = []
            for p in catalogo_componenti:
                if p.get("id_Produttori") == prod_id_selezionato:
                    cat_componente = p.get("category_id") if p.get("category_id") is not None else p.get("categoria")
                    if cat_componente is None:
                        pezzi.append(p)  
                    elif str(cat_componente) == str(category_id):
                        pezzi.append(p)  
            
            scelte_utente = {}
            model_safe_key = selected_model_name.replace(" ", "_").replace(".", "_")

            if selected_prod_name.lower() == "slot.it":
                col1_slot, col2_slot, col3_slot = st.columns(3)
                with col1_slot:
                    scelte_utente["Categoria_SlotIt"] = st.selectbox("Categoria", ["P1", "P2", "Prototipi", "Sport"], key=f"slotit_categoria_{model_safe_key}")
                with col2_slot:
                    scelte_utente["Peso_Carrozzeria"] = st.text_input("Peso Carrozzeria", value=str(edit_data.get("Peso_Carrozzeria", "")) if edit_data else "", key=f"peso_carrozzeria_{model_safe_key}")
                with col3_slot:
                    scelte_utente["Peso_Totale"] = st.text_input("Peso Totale", value=str(edit_data.get("Peso_Totale", "")) if edit_data else "", key=f"peso_totale_{model_safe_key}")
                
                slotit_campi = ["Motore", "Giri Motore", "Telaio", "Supporto Motore", "Corona", "Pignoni", "Assale Anteriore", "Assale Posteriore", "Cerchi Anteriori", "Cerchi Posteriori", "Pickup", "Viti Carrozzeria", "Stopper"]
                
                cols = st.columns(3)
                for idx, campo in enumerate(slotit_campi):
                    with cols[idx % 3]:
                        if campo == "Giri Motore":
                            scelte_utente["Giri_Motore"] = st.text_input("Giri Motore", value=str(edit_data.get("Giri_Motore", "")) if edit_data else "", key=f"giri_motore_slotit_{model_safe_key}")
                        elif campo == "Stopper":
                            scelte_utente["Stopper"] = st.selectbox("Stopper", ["No", "Sì"], key=f"slotit_stopper_{model_safe_key}")
                        else:
                            if campo == "Motore":
                                sub_pezzi = [p for p in pezzi if p.get("Prodotto") and "motore" in p.get("Prodotto").lower() and "supporto" not in p.get("Prodotto").lower()]
                            elif campo == "Supporto Motore":
                                sub_pezzi = [p for p in pezzi if p.get("Prodotto") and "supporto" in p.get("Prodotto").lower()]
                            elif campo == "Corona":
                                sub_pezzi = [p for p in pezzi if p.get("Prodotto") and "corona" in p.get("Prodotto").lower()]
                            elif campo == "Pignoni":
                                sub_pezzi = [p for p in pezzi if p.get("Prodotto") and "pignon" in p.get("Prodotto").lower()]
                            elif campo == "Telaio":
                                sub_pezzi = [p for p in pezzi if p.get("Prodotto") and "telaio" in p.get("Prodotto").lower()]
                            elif campo in ["Assale Anteriore", "Assale Posteriore"]:
                                sub_pezzi = [p for p in pezzi if p.get("Prodotto") and "assale" in p.get("Prodotto").lower()]
                            elif campo in ["Cerchi Anteriori", "Cerchi Posteriori"]:
                                sub_pezzi = [p for p in pezzi if p.get("Prodotto") and "cerch" in p.get("Prodotto").lower()]
                            elif campo == "Pickup":
                                sub_pezzi = [p for p in pezzi if p.get("Prodotto") and "pickup" in p.get("Prodotto").lower()]
                            elif campo == "Viti Carrozzeria":
                                sub_pezzi = [p for p in pezzi if p.get("Prodotto") and p.get("Prodotto").strip().lower() == "viti carrozzeria"]
                            else:
                                sub_pezzi = []

                            opzioni = []
                            for p in sub_pezzi:
                                mat = p.get('Materiale')
                                mis = p.get('Misure')
                                parte_mat = str(mat).strip() if mat and str(mat).lower() != 'none' else ""
                                parte_mis = str(mis).strip() if mis and str(mis).lower() != 'none' else ""
                                str_opt = f"{parte_mat} - {parte_mis}" if parte_mat and parte_mis else (parte_mat or parte_mis)
                                if str_opt:
                                    opzioni.append(str_opt)

                            default_idx = find_default_index(opzioni, selected_model_name)
                            scelte_utente[campo] = st.selectbox(campo, opzioni if opzioni else ["Nessuna opzione"], index=default_idx, key=f"slotit_{campo}_{model_safe_key}")

                st.write("### 🔩 Sospensioni")
                col_viti, col_tipo_sosp = st.columns(2)
                
                with col_viti:
                    sub_viti_sosp = [p for p in pezzi if p.get("Prodotto") and p.get("Prodotto").strip().lower() == "viti metriche sospensioni"]
                    opzioni_viti_sosp = []
                    for p in sub_viti_sosp:
                        mat = p.get('Materiale')
                        mis = p.get('Misure')
                        parte_mat = str(mat).strip() if mat and str(mat).lower() != 'none' else ""
                        parte_mis = str(mis).strip() if mis and str(mis).lower() != 'none' else ""
                        str_opt = f"{parte_mat} - {parte_mis}" if parte_mat and parte_mis else (parte_mat or parte_mis)
                        if str_opt:
                            opzioni_viti_sosp.append(str_opt)
                            
                    def_idx_viti = find_default_index(opzioni_viti_sosp, selected_model_name)
                    scelte_utente["Viti_Metriche_Sospensioni"] = st.selectbox("Viti Metriche Sospensioni", opzioni_viti_sosp if opzioni_viti_sosp else ["Nessuna opzione"], index=def_idx_viti, key=f"slotit_viti_metriche_sosp_{model_safe_key}")

                with col_tipo_sosp:
                    tipo_sosp_slotit = st.selectbox("Tipo Sospensione", ["Molle", "Magneti"], key=f"slotit_tipo_sospensione_{model_safe_key}")
                    scelte_utente["Tipo_Sospensione"] = tipo_sosp_slotit

                if tipo_sosp_slotit == "Magneti":
                    sub_sosp = [p for p in pezzi if p.get("Prodotto") and p.get("Prodotto").strip().lower() == "sospensioni magnetiche"]
                else:
                    sub_sosp = [p for p in pezzi if p.get("Prodotto") and p.get("Prodotto").strip().lower() == "sospensioni"]

                opzioni_sosp = []
                for p in sub_sosp:
                    mat = p.get('Materiale')
                    mis = p.get('Misure')
                    parte_mat = str(mat).strip() if mat and str(mat).lower() != 'none' else ""
                    parte_mis = str(mis).strip() if mis and str(mis).lower() != 'none' else ""
                    str_opt = f"{parte_mat} - {parte_mis}" if parte_mat and parte_mis else (parte_mat or parte_mis)
                    if str_opt:
                        opzioni_sosp.append(str_opt)

                def_idx_sosp = find_default_index(opzioni_sosp, selected_model_name)
                scelte_utente["Sospensioni"] = st.selectbox("Sospensioni", opzioni_sosp if opzioni_sosp else ["Nessuna opzione"], index=def_idx_sosp, key=f"slotit_scelta_sospensioni_{model_safe_key}")

            else:
                col_p1, col_p2, _ = st.columns(3)
                with col_p1:
                    scelte_utente["Peso_Carrozzeria"] = st.text_input("Peso Carrozzeria", value=str(edit_data.get("Peso_Carrozzeria", "")) if edit_data else "", key=f"peso_carrozzeria_{selected_prod_name}_{model_safe_key}")
                with col_p2:
                    scelte_utente["Peso_Totale"] = st.text_input("Peso Totale", value=str(edit_data.get("Peso_Totale", "")) if edit_data else "", key=f"peso_totale_{selected_prod_name}_{model_safe_key}")

                if selected_prod_name.lower() == "nsr":
                    nsr_campi = ["Motore", "Supporto Motore", "Corona", "Giri Motore", "Pignoni", "Telaio", "Assale Anteriore", "Assale Posteriore", "Cerchi Anteriori", "Cerchi Posteriori", "Pickup", "Viti Carrozzeria"]
                    
                    cols = st.columns(3)
                    for idx, campo in enumerate(nsr_campi):
                        with cols[idx % 3]:
                            if campo == "Giri Motore":
                                scelte_utente["Giri_Motore"] = st.text_input("Giri Motore", value=str(edit_data.get("Giri_Motore", "")) if edit_data else "", key=f"giri_motore_nsr_{model_safe_key}")
                            else:
                                if campo == "Motore":
                                    sub_pezzi = [p for p in pezzi if p.get("Prodotto") and "motore" in p.get("Prodotto").lower() and "supporto" not in p.get("Prodotto").lower()]
                                elif campo == "Supporto Motore":
                                    sub_pezzi = [p for p in pezzi if p.get("Prodotto") and "supporto" in p.get("Prodotto").lower()]
                                elif campo == "Corona":
                                    sub_pezzi = [p for p in pezzi if p.get("Prodotto") and "corona" in p.get("Prodotto").lower()]
                                elif campo == "Pignoni":
                                    sub_pezzi = [p for p in pezzi if p.get("Prodotto") and "pignon" in p.get("Prodotto").lower()]
                                elif campo == "Telaio":
                                    sub_pezzi = [p for p in pezzi if p.get("Prodotto") and "telaio" in p.get("Prodotto").lower()]
                                elif campo in ["Assale Anteriore", "Assale Posteriore"]:
                                    sub_pezzi = [p for p in pezzi if p.get("Prodotto") and "assale" in p.get("Prodotto").lower()]
                                elif campo in ["Cerchi Anteriori", "Cerchi Posteriori"]:
                                    sub_pezzi = [p for p in pezzi if p.get("Prodotto") and "cerch" in p.get("Prodotto").lower()]
                                elif campo == "Pickup":
                                    sub_pezzi = [p for p in pezzi if p.get("Prodotto") and "pickup" in p.get("Prodotto").lower()]
                                elif campo == "Viti Carrozzeria":
                                    sub_pezzi = [p for p in pezzi if p.get("Prodotto") and ("viti" in p.get("Prodotto").lower() or "carrozzeria" in p.get("Prodotto").lower())]
                                else:
                                    sub_pezzi = []

                                opzioni = []
                                for p in sub_pezzi:
                                    mat = p.get('Materiale')
                                    mis = p.get('Misure')
                                    parte_mat = str(mat).strip() if mat and str(mat).lower() != 'none' else ""
                                    parte_mis = str(mis).strip() if mis and str(mis).lower() != 'none' else ""
                                    str_opt = f"{parte_mat} - {parte_mis}" if parte_mat and parte_mis else (parte_mat or parte_mis)
                                    if str_opt:
                                        opzioni.append(str_opt)

                                def_idx = find_default_index(opzioni, selected_model_name)
                                scelte_utente[campo] = st.selectbox(campo, opzioni if opzioni else ["Nessuna opzione"], index=def_idx, key=f"nsr_{campo}_{model_safe_key}")

                    st.write("### 🔩 Sospensioni")
                    sosp_nsr_attive = st.selectbox("Sospensioni", ["No", "Sì"], key=f"nsr_sosp_sino_{model_safe_key}")
                    scelte_utente["Sospensioni"] = sosp_nsr_attive
                    if sosp_nsr_attive == "Sì":
                        scelte_utente["Tipo_Molla_NSR"] = st.selectbox("Tipo Molla", ["Molle Hard", "Molle Medium", "Molle Soft"], key=f"nsr_tipo_molla_{model_safe_key}")

                elif selected_prod_name.lower() == "thunderslot":
                    thunder_campi = ["Motore", "Supporto Motore", "Corona", "Giri Motore", "Telaio", "Cerchi Anteriori", "Cerchi Posteriori", "Viti Carrozzeria", "Assale"]
                    
                    cols = st.columns(3)
                    for idx, campo in enumerate(thunder_campi):
                        with cols[idx % 3]:
                            if campo == "Giri Motore":
                                scelte_utente["Giri_Motore"] = st.text_input("Giri Motore", value=str(edit_data.get("Giri_Motore", "")) if edit_data else "", key=f"giri_motore_thunderslot_{model_safe_key}")
                            else:
                                if campo == "Motore":
                                    sub_pezzi = [p for p in pezzi if p.get("Prodotto") and "motore" in p.get("Prodotto").lower() and "supporto" not in p.get("Prodotto").lower()]
                                elif campo == "Supporto Motore":
                                    sub_pezzi = [p for p in pezzi if p.get("Prodotto") and "supporto" in p.get("Prodotto").lower()]
                                elif campo == "Corona":
                                    sub_pezzi = [p for p in pezzi if p.get("Prodotto") and "corona" in p.get("Prodotto").lower()]
                                elif campo == "Telaio":
                                    sub_pezzi = [p for p in pezzi if p.get("Prodotto") and "telaio" in p.get("Prodotto").lower()]
                                elif campo in ["Cerchi Anteriori", "Cerchi Posteriori"]:
                                    sub_pezzi = [p for p in pezzi if p.get("Prodotto") and "cerch" in p.get("Prodotto").lower()]
                                elif campo == "Viti Carrozzeria":
                                    sub_pezzi = [p for p in pezzi if p.get("Prodotto") and ("viti" in p.get("Prodotto").lower() or "carrozzeria" in p.get("Prodotto").lower())]
                                elif campo == "Assale":
                                    sub_pezzi = [p for p in pezzi if p.get("Prodotto") and "assale" in p.get("Prodotto").lower()]
                                else:
                                    sub_pezzi = []

                                opzioni = []
                                for p in sub_pezzi:
                                    mat = p.get('Materiale')
                                    mis = p.get('Misure')
                                    parte_mat = str(mat).strip() if mat and str(mat).lower() != 'none' else ""
                                    parte_mis = str(mis).strip() if mis and str(mis).lower() != 'none' else ""
                                    str_opt = f"{parte_mat} - {parte_mis}" if parte_mat and parte_mis else (parte_mat or parte_mis)
                                    if str_opt:
                                        opzioni.append(str_opt)

                                def_idx = find_default_index(opzioni, selected_model_name)
                                scelte_utente[campo] = st.selectbox(campo, opzioni if opzioni else ["Nessuna opzione"], index=def_idx, key=f"thunder_{campo}_{model_safe_key}")

                    # --- SEZIONE SOSPENSIONI THUNDERSLOT ---
                    st.write("### 🔩 Sospensioni Thunderslot")
                    col_sosp1, col_sosp2, col_sosp3 = st.columns(3)
                    
                    tipi_sospensioni_thunderslot = ["Posteriori", "Laterali", "Anteriori"]
                    
                    for i, tipo_sosp in enumerate(tipi_sospensioni_thunderslot):
                        col_corrente = [col_sosp1, col_sosp2, col_sosp3][i]
                        key_base = tipo_sosp.lower()
                        
                        with col_corrente:
                            st.markdown(f"**Sospensioni {tipo_sosp}**")
                            sosp_attive = st.selectbox("Stato", ["No", "Sì"], key=f"thunder_sosp_{key_base}_sino_{model_safe_key}")
                            scelte_utente[f"Sospensioni_{tipo_sosp}"] = sosp_attive
                            
                            if sosp_attive == "Sì":
                                tipo_materiale_sosp = st.selectbox("Tipo", ["Molle", "Spugna"], key=f"thunder_sosp_{key_base}_tipo_{model_safe_key}")
                                scelte_utente[f"Tipo_Sospensione_{tipo_sosp}"] = tipo_materiale_sosp
                                
                                if tipo_materiale_sosp == "Molle":
                                    durezza_molla = st.selectbox("Durezza", ["Molle morbide", "Molle medie", "Molle dure"], key=f"thunder_sosp_{key_base}_durezza_{model_safe_key}")
                                    scelte_utente[f"Durezza_Molla_{tipo_sosp}"] = durezza_molla

                else:
                    priorita = ["Motore", "Corona Sidewinder", "Pignone"]
                    altre_tipologie = [
                        t for t in list(set([p.get("Prodotto") for p in pezzi if p.get("Prodotto")]))
                        if t not in priorita and t not in ["Sospensioni", "Cuscinetti a flangia sin", "Bronzine"]
                        and "distanzial" not in t.lower()
                    ]
                    tutte_le_principali = [p for p in priorita if any(x.get("Prodotto") == p for x in pezzi)] + altre_tipologie
                    
                    cols = st.columns(3)
                    for i, tipologia in enumerate(tutte_le_principali):
                        opzioni = []
                        for p in pezzi:
                            if p.get("Prodotto") == tipologia:
                                mat = p.get('Materiale')
                                mis = p.get('Misure')
                                parte_mat = str(mat).strip() if mat and str(mat).lower() != 'none' else ""
                                parte_mis = str(mis).strip() if mis and str(mis).lower() != 'none' else ""
                                str_opt = f"{parte_mat} - {parte_mis}" if parte_mat and parte_mis else (parte_mat or parte_mis)
                                if str_opt:
                                    opzioni.append(str_opt)

                        def_idx = find_default_index(opzioni, selected_model_name)
                        with cols[i % 3]:
                            scelte_utente[tipologia] = st.selectbox(tipologia, opzioni if opzioni else ["Nessuna opzione"], index=def_idx, key=f"comp_{tipologia}_{model_safe_key}")

            st.divider()

            if selected_prod_name.lower() == "slot.it":
                st.write("### 📏 Distanziali")
                col_d_pick = st.columns(1)[0]
                with col_d_pick:
                    dist_pick_attive = st.selectbox("Distanziale Pickup", ["No", "Sì"], key=f"dist_pick_si_no_{model_safe_key}")
                    scelte_utente["Distanziali_Pickup"] = dist_pick_attive
                    if dist_pick_attive == "Sì":
                        lista_dist_pick = []
                        for p in pezzi:
                            if p.get('Prodotto') and p.get('Prodotto').strip().lower() == "distanziale pickup":
                                mat = p.get('Materiale')
                                mis = p.get('Misure')
                                parte_mat = str(mat).strip() if mat and str(mat).lower() != 'none' else ""
                                parte_mis = str(mis).strip() if mis and str(mis).lower() != 'none' else ""
                                str_opt = f"{parte_mat} - {parte_mis}" if parte_mat and parte_mis else (parte_mat or parte_mis)
                                if str_opt:
                                    lista_dist_pick.append(str_opt)

                        def_idx_dpic = find_default_index(lista_dist_pick, selected_model_name)
                        scelte_utente["Distanziale_Pickup"] = st.selectbox("Seleziona Distanziale Pickup", lista_dist_pick if lista_dist_pick else ["Nessun distanziale disponibile"], index=def_idx_dpic, key=f"sel_dist_pick_{model_safe_key}")
            else:
                st.write("### 📏 Distanziali")
                col_d1, col_d2, col_d3 = st.columns(3)
                
                with col_d1:
                    dist_ant_attive = st.selectbox("Distanziali anteriori", ["No", "Sì"], key=f"dist_ant_si_no_{model_safe_key}")
                    scelte_utente["Distanziali_Anteriori"] = dist_ant_attive
                    if dist_ant_attive == "Sì":
                        lista_dist_ant = []
                        for p in pezzi:
                            if p.get('Prodotto') and "distanzial" in p.get('Prodotto').lower() and "pickup" not in p.get('Prodotto').lower():
                                mat = p.get('Materiale')
                                mis = p.get('Misure')
                                parte_mat = str(mat).strip() if mat and str(mat).lower() != 'none' else ""
                                parte_mis = str(mis).strip() if mis and str(mis).lower() != 'none' else ""
                                str_opt = f"{parte_mat} - {parte_mis}" if parte_mat and parte_mis else (parte_mat or parte_mis)
                                if str_opt:
                                    lista_dist_ant.append(str_opt)

                        def_idx_da = find_default_index(lista_dist_ant, selected_model_name)
                        scelte_utente["Distanziale_Anteriore"] = st.selectbox("Seleziona Distanziale Anteriore", lista_dist_ant if lista_dist_ant else ["Nessun distanziale disponibile"], index=def_idx_da, key=f"sel_dist_ant_{model_safe_key}")

                with col_d2:
                    dist_post_attive = st.selectbox("Distanziali posteriori", ["No", "Sì"], key=f"dist_post_si_no_{model_safe_key}")
                    scelte_utente["Distanziali_Posteriori"] = dist_post_attive
                    if dist_post_attive == "Sì":
                        lista_dist_post = []
                        for p in pezzi:
                            if p.get('Prodotto') and "distanzial" in p.get('Prodotto').lower() and "pickup" not in p.get('Prodotto').lower():
                                mat = p.get('Materiale')
                                mis = p.get('Misure')
                                parte_mat = str(mat).strip() if mat and str(mat).lower() != 'none' else ""
                                parte_mis = str(mis).strip() if mis and str(mis).lower() != 'none' else ""
                                str_opt = f"{parte_mat} - {parte_mis}" if parte_mat and parte_mis else (parte_mat or parte_mis)
                                if str_opt:
                                    lista_dist_post.append(str_opt)

                        def_idx_dp = find_default_index(lista_dist_post, selected_model_name)
                        scelte_utente["Distanziale_Posteriore"] = st.selectbox("Seleziona Distanziale Posteriore", lista_dist_post if lista_dist_post else ["Nessun distanziale disponibile"], index=def_idx_dp, key=f"sel_dist_post_{model_safe_key}")

                with col_d3:
                    dist_pick_attive = st.selectbox("Distanziale Pickup", ["No", "Sì"], key=f"dist_pick_si_no_{model_safe_key}")
                    scelte_utente["Distanziali_Pickup"] = dist_pick_attive
                    if dist_pick_attive == "Sì":
                        lista_dist_pick = []
                        for p in pezzi:
                            if p.get('Prodotto') and p.get('Prodotto').strip().lower() == "distanziale pickup":
                                mat = p.get('Materiale')
                                mis = p.get('Misure')
                                parte_mat = str(mat).strip() if mat and str(mat).lower() != 'none' else ""
                                parte_mis = str(mis).strip() if mis and str(mis).lower() != 'none' else ""
                                str_opt = f"{parte_mat} - {parte_mis}" if parte_mat and parte_mis else (parte_mat or parte_mis)
                                if str_opt:
                                    lista_dist_pick.append(str_opt)

                        def_idx_dpic = find_default_index(lista_dist_pick, selected_model_name)
                        scelte_utente["Distanziale_Pickup"] = st.selectbox("Seleziona Distanziale Pickup", lista_dist_pick if lista_dist_pick else ["Nessun distanziale disponibile"], index=def_idx_dpic, key=f"sel_dist_pick_{model_safe_key}")

            st.divider()

            st.write("### 🔩 Supporto Assale")
            if selected_prod_name.lower() == "nsr":
                scelte_utente["Tipo_Supporto"] = "Bronzine"
                lista_bronzine = []
                for p in pezzi:
                    if p.get('Prodotto') and "bronz" in p.get('Prodotto').lower():
                        mat = p.get('Materiale')
                        mis = p.get('Misure')
                        parte_mat = str(mat).strip() if mat and str(mat).lower() != 'none' else ""
                        parte_mis = str(mis).strip() if mis and str(mis).lower() != 'none' else ""
                        str_opt = f"{parte_mat} - {parte_mis}" if parte_mat and parte_mis else (parte_mat or parte_mis)
                        if str_opt:
                            lista_bronzine.append(str_opt)

                def_idx_bronz = find_default_index(lista_bronzine, selected_model_name)
                scelte_utente["Dettaglio_Supporto"] = st.selectbox("Seleziona Bronzine", lista_bronzine if lista_bronzine else ["Nessuna bronzina disponibile"], index=def_idx_bronz, key=f"sel_bronzine_{model_safe_key}")
            else:
                scelta_tipo_supp = st.selectbox("Seleziona componente", ["Bronzine", "Cuscinetti"], key=f"scelta_bronz_cusc_{model_safe_key}")
                scelte_utente["Tipo_Supporto"] = scelta_tipo_supp

                if scelta_tipo_supp == "Bronzine":
                    lista_bronzine = []
                    for p in pezzi:
                        if p.get('Prodotto') and "bronz" in p.get('Prodotto').lower():
                            mat = p.get('Materiale')
                            mis = p.get('Misure')
                            parte_mat = str(mat).strip() if mat and str(mat).lower() != 'none' else ""
                            parte_mis = str(mis).strip() if mis and str(mis).lower() != 'none' else ""
                            str_opt = f"{parte_mat} - {parte_mis}" if parte_mat and parte_mis else (parte_mat or parte_mis)
                            if str_opt:
                                lista_bronzine.append(str_opt)

                    def_idx_bronz = find_default_index(lista_bronzine, selected_model_name)
                    scelte_utente["Dettaglio_Supporto"] = st.selectbox("Seleziona Bronzine", lista_bronzine if lista_bronzine else ["Nessuna bronzina disponibile"], index=def_idx_bronz, key=f"sel_bronzine_{model_safe_key}")
                else:
                    lista_cuscinetti = []
                    for p in pezzi:
                        if p.get('Prodotto') and "cuscinett" in p.get('Prodotto').lower():
                            mat = p.get('Materiale')
                            mis = p.get('Misure')
                            parte_mat = str(mat).strip() if mat and str(mat).lower() != 'none' else ""
                            parte_mis = str(mis).strip() if mis and str(mis).lower() != 'none' else ""
                            str_opt = f"{parte_mat} - {parte_mis}" if parte_mat and parte_mis else (parte_mat or parte_mis)
                            if str_opt:
                                lista_cuscinetti.append(str_opt)

                    def_idx_cusc = find_default_index(lista_cuscinetti, selected_model_name)
                    scelte_utente["Dettaglio_Supporto"] = st.selectbox("Seleziona Cuscinetti", lista_cuscinetti if lista_cuscinetti else ["Nessun cuscinetto disponibile"], index=def_idx_cusc, key=f"sel_cuscinetti_{model_safe_key}")

            st.divider()

            scelte_utente["Note"] = st.text_area("Note", value=str(edit_data.get("Note", "")) if edit_data else "", height=120, key=f"note_setup_generale_{model_safe_key}")

            st.divider()

            if st.session_state.modifying_config_id:
                st.markdown("### 🚗 Aggiorna Configurazione nel Garage")
                default_nome_mod = st.session_state.modifying_config_name if "modifying_config_name" in st.session_state else ""
                nome_configurazione_input = st.text_input("Nome Configurazione", value=default_nome_mod, key=f"nome_config_mod_{model_safe_key}")
                
                col_upd1, col_upd2 = st.columns(2)
                with col_upd1:
                    if st.button("💾 Salva Modifiche"):
                        if not nome_configurazione_input:
                            st.warning("Inserisci un nome per la configurazione.")
                        else:
                            try:
                                record_garage = {
                                    "nome_configurazione": nome_configurazione_input,
                                    "modello_nome": selected_model_name,
                                    "dettagli_setup": str(scelte_utente)
                                }
                                supabase.table("IlMioGarage").update(record_garage).eq("id", st.session_state.modifying_config_id).execute()
                                st.success(f"Configurazione '{nome_configurazione_input}' aggiornata con successo!")
                                st.session_state.modifying_config_id = None
                                st.session_state.modifying_data = None
                                st.session_state.active_tab = "🚗 Il Mio Garage"
                                st.rerun()
                            except Exception as e:
                                st.error(f"Errore durante l'aggiornamento: {e}")
                with col_upd2:
                    if st.button("❌ Annulla Modifica"):
                        st.session_state.modifying_config_id = None
                        st.session_state.modifying_data = None
                        st.session_state.active_tab = "🚗 Il Mio Garage"
                        st.rerun()
            else:
                st.markdown("### 🚗 Salva nel Mio Garage Personale")
                nome_configurazione_input = st.text_input("Nome Configurazione (es. Corvette Monza Gara)", key=f"nome_config_{model_safe_key}")
                
                if st.button("💾 Salva nel Mio Garage"):
                    if not nome_configurazione_input:
                        st.warning("Inserisci un nome per la configurazione prima di salvare nel Garage.")
                    else:
                        try:
                            record_garage = {
                                "nome_configurazione": nome_configurazione_input,
                                "modello_nome": selected_model_name,
                                "dettagli_setup": str(scelte_utente)
                            }
                            supabase.table("IlMioGarage").insert(record_garage).execute()
                            st.success(f"Configurazione '{nome_configurazione_input}' salvata con successo nel tuo Garage!")
                        except Exception as e:
                            st.error(f"Errore durante il salvataggio nel Garage: {e}")
        else:
            st.info("Seleziona prima un produttore specifico nei filtri in alto per accedere al setup avanzato.")
    else:
        st.info("Seleziona un modello tra i filtri in alto per configurarlo.")

elif st.session_state.active_tab == "➕ Carica Modello":
    st.subheader("Inserisci Nuovo Modello")
    with st.form("form_nuovo_modello"):
        nuovo_modello = st.text_input("Nome Modello")
        foto_modello = st.text_input("URL Immagine Modello (es. link pubblico Supabase Storage)")
        
        prod_form_list = {p.get("name"): p.get("id") for p in produttori if p.get("name") and p.get("id")}
        cat_form_list = {c.get("name"): c.get("id") for c in categorie if c.get("name") and c.get("id")}
        
        scelta_produttore = st.selectbox("Produttore", list(prod_form_list.keys()) if prod_form_list else [])
        scelta_categoria = st.selectbox("Categoria", list(cat_form_list.keys()) if cat_form_list else [])
        
        submitted = st.form_submit_button("Salva nel Database")
        
        if submitted and nuovo_modello:
            try:
                id_cat_scelta = cat_form_list.get(scelta_categoria)
                nuovo_record = {
                    "name": nuovo_modello,
                    "category_id": id_cat_scelta,
                    "foto_url": foto_modello
                }
                supabase.table("MODELLI").insert(nuovo_record).execute()
                st.success(f"Modello '{nuovo_modello}' salvato con successo!")
                st.rerun()
            except Exception as e:
                st.error(f"Errore durante il salvataggio: {e}")

elif st.session_state.active_tab == "🚗 Il Mio Garage":
    st.subheader("🚗 Il Mio Garage - Configurazioni Salvate")
    
    try:
        response_garage = supabase.table("IlMioGarage").select("*").execute()
        salvati = response_garage.data if response_garage.data else []
        
        if salvati:
            for s in salvati:
                conf_id = s.get('id')
                conf_nome = s.get('nome_configurazione', 'Configurazione senza nome')
                conf_modello = s.get('modello_nome', 'Modello non specificato')
                
                dettagli_str = s.get('dettagli_setup', '{}')
                dict_dettagli = {}
                try:
                    dict_dettagli = ast.literal_eval(dettagli_str) if isinstance(dettagli_str, str) else dettagli_str
                except Exception:
                    dict_dettagli = {"Dettagli": dettagli_str}

                match_modello = next((m for m in modelli if m.get("name") == conf_modello), None)
                foto_auto_url = match_modello.get("foto_url") if match_modello else None

                # Riga con nome configurazione e 3 pulsanti affiancati all'esterno: PDF, Modifica, Elimina
                col_info, col_btn_pdf, col_btn_mod, col_btn_del = st.columns([4, 2, 2, 2])
                with col_info:
                    st.markdown(f"**🏎️ {conf_nome}** — *(Modello: {conf_modello})*")
                
                with col_btn_pdf:
                    try:
                        pdf_bytes = generate_pdf(
                            conf_nome, 
                            conf_modello, 
                            dict_dettagli if isinstance(dict_dettagli, dict) else {"Dettagli": dettagli_str},
                            foto_url=foto_auto_url
                        )
                        st.download_button(
                            label=f"⬇️ PDF",
                            data=pdf_bytes,
                            file_name=f"{conf_nome.replace(' ', '_')}_scheda_tecnica.pdf",
                            mime="application/pdf",
                            key=f"download_pdf_{conf_id}"
                        )
                    except Exception as e:
                        st.error(f"Errore PDF")

                with col_btn_mod:
                    if st.button("✏️ Modifica", key=f"edit_conf_{conf_id}"):
                        st.session_state.modifying_config_id = conf_id
                        st.session_state.modifying_config_name = conf_nome
                        dettagli_str_init = s.get('dettagli_setup', '{}')
                        try:
                            st.session_state.modifying_data = ast.literal_eval(dettagli_str_init) if isinstance(dettagli_str_init, str) else dettagli_str_init
                        except Exception:
                            st.session_state.modifying_data = {}
                        st.session_state.active_tab = "📋 Visualizza Modelli"
                        st.rerun()

                with col_btn_del:
                    if st.button("🗑️ Elimina", key=f"del_conf_{conf_id}"):
                        try:
                            supabase.table("IlMioGarage").delete().eq("id", conf_id).execute()
                            st.success("Configurazione eliminata con successo!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Errore durante l'eliminazione: {e}")
                
                # Expander sottostante per i soli dettagli visivi e immagine
                with st.expander(f"Visualizza dettagli di {conf_nome}"):
                    if foto_auto_url:
                        try:
                            st.image(foto_auto_url, width=200)
                        except Exception:
                            pass
                    
                    if isinstance(dict_dettagli, dict):
                        for k, v in dict_dettagli.items():
                            st.write(f"- **{k}:** {v}")
                    else:
                        st.write(dettagli_str)
                
                st.markdown("---")
        else:
            st.info("Nessuna configurazione salvata nel garage al momento.")
    except Exception as e:
        st.error(f"Errore durante il caricamento del garage da Supabase: {e}")
