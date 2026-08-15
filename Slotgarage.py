import ast
import os
import time
import tempfile
from fpdf import FPDF
import requests
import streamlit as st
import streamlit.components.v1 as components
from supabase import create_client

LOGO_PATH = "logo.png"

# --- CONFIGURAZIONE PAGINA (PRIMISSIMA ISTRUZIONE STREAMLIT) ---
st.set_page_config(page_title="SlotGarage", page_icon=LOGO_PATH, layout="wide")

# --- CONFIGURAZIONE SUPABASE & SICUREZZA ---
try:
    SUPABASE_URL = st.secrets["supabase"]["url"]
    SUPABASE_KEY = st.secrets["supabase"]["key"]
except Exception:
    SUPABASE_URL = "https://rmfaphfksvcyynfrrbsy.supabase.co"
    SUPABASE_KEY = "sb_publishable_vp-3OcwsKymyHEgP8XlbsQ_KVFQh0I6"

@st.cache_resource
def init_connection():
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        st.error(f"Errore di connessione a Supabase: {e}")
        return None

supabase = init_connection()

# --- INIEZIONE AVANZATA META TAG PER PWA & MOBILE ---
components.html(
    """
    <script>
        const docHead = window.parent.document.head;
        
        const existingLinks = docHead.querySelectorAll('link[rel="apple-touch-icon"], link[rel="manifest"]');
        existingLinks.forEach(el => el.remove());

        const manifestLink = window.parent.document.createElement('link');
        manifestLink.rel = 'manifest';
        manifestLink.href = 'manifest.json';
        docHead.appendChild(manifestLink);

        const appleIcon = window.parent.document.createElement('link');
        appleIcon.rel = 'apple-touch-icon';
        appleIcon.href = 'logo.png';
        docHead.appendChild(appleIcon);

        const metaName = window.parent.document.createElement('meta');
        metaName.name = 'apple-mobile-web-app-title';
        metaName.content = 'SlotGarage';
        docHead.appendChild(metaName);
        
        const metaCapable = window.parent.document.createElement('meta');
        metaCapable.name = 'apple-mobile-web-app-capable';
        metaCapable.content = 'yes';
        docHead.appendChild(metaCapable);
    </script>
""",
    height=0,
)

# --- INTESTAZIONE CON LOGO E SCRITTA INGRANDITA E ABBASSATA ---
col_logo, col_titolo = st.columns([2, 10])
with col_logo:
    try:
        st.image(LOGO_PATH, width=220)
    except Exception:
        st.write("🏎️")
with col_titolo:
    st.markdown(
        "<h1 style='margin-top: 25px; font-size: 4.2rem; margin-bottom: 0px;'>SlotGarage</h1><p style='color: #FFD700; font-size: 1.3rem; margin-top: 0px;'>Creato da Emanuele Palena</p>",
        unsafe_allow_html=True,
    )

if not supabase:
    st.error("Errore di connessione a Supabase.")
    st.stop()

# --- CARICAMENTO DATI RESILIENTE (OTTIMIZZATO CON TTL 300s) ---
@st.cache_data(ttl=300)
def get_data(table_name):
    if not supabase:
        return []
    try:
        response = supabase.table(table_name).select("*").execute()
        return response.data if response and response.data else []
    except Exception as e:
        st.warning(f"Impossibile caricare i dati dalla tabella {table_name}: {e}")
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
if "modifying_config_name" not in st.session_state:
    st.session_state.modifying_config_name = ""
if "modifying_pulsante_id" not in st.session_state:
    st.session_state.modifying_pulsante_id = None
if "modifying_pulsante_data" not in st.session_state:
    st.session_state.modifying_pulsante_data = None
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "📋 Visualizza Modelli"

# --- SEZIONE FILTRI E SELEZIONE ---
st.header("🔍 Navigazione e Filtri")

prod_options = {p.get("name"): p.get("id") for p in produttori if p and p.get("name") and p.get("id")}

default_prod_idx = 0
default_cat_idx = 0
default_mod_idx = 0

pre_selected_prod = "Tutti"
pre_selected_cat = "Tutte"
pre_selected_mod = "Tutti"

if st.session_state.modifying_config_id and st.session_state.get("modifying_model_name"):
    mod_name_target = st.session_state.get("modifying_model_name")
    m_obj = next((m for m in modelli if m and m.get("name") == mod_name_target), None)
    if m_obj:
        pre_selected_mod = m_obj.get("name")
        cat_id_target = m_obj.get("category_id")
        c_obj = next((c for c in categorie if c and c.get("id") == cat_id_target), None)
        if c_obj:
            pre_selected_cat = c_obj.get("name")
            prod_id_target = c_obj.get("brand_it")
            p_obj = next((p for p in produttori if p and p.get("id") == prod_id_target), None)
            if p_obj:
                pre_selected_prod = p_obj.get("name")

col_f1, col_f2, col_f3 = st.columns(3)

prod_names_list = ["Tutti"] + list(prod_options.keys())
if pre_selected_prod in prod_names_list:
    default_prod_idx = prod_names_list.index(pre_selected_prod)

with col_f1:
    selected_prod_name = st.selectbox("Seleziona Produttore", prod_names_list, index=default_prod_idx)

if selected_prod_name != "Tutti":
    prod_id = prod_options[selected_prod_name]
    cat_options = {c.get("name"): c.get("id") for c in categorie if c and c.get("brand_it") == prod_id}
else:
    cat_options = {c.get("name"): c.get("id") for c in categorie if c and c.get("name") and c.get("id")}

cat_names_list = ["Tutte"] + list(cat_options.keys())
if pre_selected_cat in cat_names_list:
    default_cat_idx = cat_names_list.index(pre_selected_cat)

with col_f2:
    selected_cat_name = st.selectbox("Seleziona Categoria", cat_names_list, index=default_cat_idx)

if selected_cat_name != "Tutte":
    cat_id = cat_options[selected_cat_name]
    mod_list = [m.get("name") for m in modelli if m and m.get("category_id") == cat_id and m.get("name")]
else:
    mod_list = [m.get("name") for m in modelli if m and m.get("name")]

mod_names_list = ["Tutti"] + mod_list
if pre_selected_mod in mod_names_list:
    default_mod_idx = mod_names_list.index(pre_selected_mod)

with col_f3:
    selected_model_name = st.selectbox("Seleziona Modello", mod_names_list, index=default_mod_idx)

st.divider()

# --- MENU DI NAVIGAZIONE GESTITO VIA STATO ---
tabs_list = ["📋 Visualizza Modelli", "🚗 Il Mio Garage", "🎛️ Il Mio Pulsante", "➕ Carica Modello"]
selected_tab = st.radio(
    "Navigazione",
    tabs_list,
    index=tabs_list.index(st.session_state.active_tab) if st.session_state.active_tab in tabs_list else 0,
    horizontal=True,
    label_visibility="collapsed"
)
st.session_state.active_tab = selected_tab
st.divider()

def find_default_index(opzioni, model_name, target_value=None):
    if target_value and target_value in opzioni:
        return opzioni.index(target_value)
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

def upload_image_to_supabase(uploaded_file):
    if uploaded_file is None:
        return None
    try:
        file_ext = uploaded_file.name.split('.')[-1]
        file_name = f"car_{int(time.time())}_{os.urandom(2).hex()}.{file_ext}"
        file_bytes = uploaded_file.getvalue()
        
        supabase.storage.from_("immagini-garage").upload(
            path=file_name,
            file=file_bytes,
            file_options={"content-type": uploaded_file.type}
        )
        
        public_url_res = supabase.storage.from_("immagini-garage").get_public_url(file_name)
        return public_url_res
    except Exception as e:
        st.error(f"Errore durante il caricamento dell'immagine nel cloud: {e}")
        return None

def generate_pdf(config_name, modello_nome, dettagli, foto_url=None):
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    
    bg_dark = (30, 32, 36)
    accent_bar = (220, 50, 50)
    text_dark = (40, 40, 40)
    text_light = (255, 255, 255)
    
    pdf.set_fill_color(250, 252, 255)
    pdf.rect(0, 0, 297, 210, 'F')
    
    pdf.set_fill_color(*bg_dark)
    pdf.rect(0, 0, 297, 16, 'F')
    pdf.set_fill_color(*accent_bar)
    pdf.rect(0, 16, 297, 2, 'F')
    
    pdf.set_text_color(*text_light)
    pdf.set_font("Helvetica", "B", 10)
    
    pdf.set_xy(10, 4.5)
    pdf.cell(150, 7, f"SLOTGARAGE  |  SCHEDA: {config_name.upper()}", ln=0)
    
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_xy(140, 4.5)
    pdf.cell(147, 7, "Generato con Slotgarage di Palena Emanuele", ln=1, align="R")
    
    left_x = 10
    left_w = 85
    current_y = 22
    
    pdf.set_text_color(*text_dark)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_xy(left_x, current_y)
    pdf.cell(left_w, 6, f"Modello: {modello_nome}", ln=True)
    current_y += 7
    
    if foto_url:
        img_file_obj = None
        try:
            if foto_url.startswith("http"):
                response_img = requests.get(foto_url, timeout=5)
                if response_img.status_code == 200:
                    img_file_obj = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                    img_file_obj.write(response_img.content)
                    img_file_obj.close()
                    pdf.image(img_file_obj.name, x=left_x+2, y=current_y, w=left_w-4)
                    current_y += 48
            else:
                if os.path.exists(foto_url):
                    pdf.image(foto_url, x=left_x+2, y=current_y, w=left_w-4)
                    current_y += 48
        except Exception:
            pass
        finally:
            if img_file_obj and os.path.exists(img_file_obj.name):
                try:
                    os.remove(img_file_obj.name)
                except Exception:
                    pass
                    
    current_y += 4
    
    col_w = 93
    col1_x = 98
    col2_x = 194
    
    pesi_motore_Keys = ["Peso_Carrozzeria", "Peso_Totale", "Giri_Motore", "Motore", "Supporto Motore", "Corona", "Pignoni"]
    
    dettagli_filtrati = {}
    for k, v in dettagli.items():
        if k.lower() == "note" or k.lower() == "foto_personalizzata_url":
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
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_xy(x, y)
        pdf.cell(w, 6, f"   {title}", ln=True, fill=True)
        
        item_y = y + 7.5
        for k, v in items_dict.items():
            pdf.set_text_color(*text_dark)
            pdf.set_font("Helvetica", "", 8.5)
            k_clean = str(k).replace("_", " ")
            v_clean = str(v)
            
            pdf.set_xy(x + 3, item_y)
            pdf.cell(34, 4.8, f"{k_clean}:", 0, 0)
            
            pdf.set_font("Helvetica", "B", 8.5)
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
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_xy(col1_x, next_y)
        pdf.cell(189, 5, "   NOTE DI SETTING / COLLAUDO", ln=True, fill=True)
        
        pdf.set_text_color(*text_dark)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_xy(col1_x + 3, next_y + 5.5)
        pdf.multi_cell(183, 4, str(note_val))
        
    return pdf.output(dest='S').encode('latin-1', 'replace')

# --- GESTIONE SEZIONI (TAB) ---

if st.session_state.active_tab == "📋 Visualizza Modelli":
    if selected_model_name != "Tutti":
        modello_selezionato = next((m for m in modelli if m and m.get("name") == selected_model_name), None)
        modello_id = modello_selezionato.get("id") if modello_selezionato else None
        category_id = cat_options.get(selected_cat_name) if selected_cat_name in cat_options else None
        prod_id_selezionato = prod_options.get(selected_prod_name) if selected_prod_name in prod_options else None
        
        edit_data = st.session_state.modifying_data if st.session_state.modifying_config_id else {}
        
        if st.session_state.modifying_config_id:
            st.warning(f"⚠️ Stai modificando la configurazione esistente: **{st.session_state.get('modifying_config_name', '')}**. Modifica i parametri desiderati e clicca su 'Salva Modifiche' in fondo alla pagina per confermare.")
            
        st.subheader(f"Configurazione: {selected_model_name}")
        
        default_foto_db = modello_selezionato.get("foto_url") if modello_selezionato else None
        if default_foto_db:
            try:
                st.image(default_foto_db, caption=f"Foto di default: {selected_model_name}", width=250)
            except Exception:
                pass
                
        st.markdown("### 📸 Foto Personalizzata del Tuo Modello (Opzionale)")
        col_foto_up1, col_foto_up2 = st.columns(2)
        with col_foto_up1:
            file_foto_pers = st.file_uploader("Carica immagine dal dispositivo", type=["jpg", "jpeg", "png"], key="file_foto_pers_setup")
        with col_foto_up2:
            url_foto_pers = st.text_input("O inserisci URL immagine personalizzata", value=str(edit_data.get("foto_personalizzata_url", "")) if edit_data and "foto_personalizzata_url" in edit_data else "", key="url_foto_pers_setup")
            
        foto_personalizzata_finale = url_foto_pers
        if file_foto_pers is not None:
            with st.spinner("Caricamento immagine nel cloud in corso..."):
                uploaded_cloud_url = upload_image_to_supabase(file_foto_pers)
                if uploaded_cloud_url:
                    foto_personalizzata_finale = uploaded_cloud_url
                    st.success("Immagine caricata con successo nel cloud!")
        elif not url_foto_pers and edit_data and "foto_personalizzata_url" in edit_data:
            foto_personalizzata_finale = edit_data.get("foto_personalizzata_url")
            
        if foto_personalizzata_finale:
            try:
                st.image(foto_personalizzata_finale, caption="Anteprima Foto Personalizzata", width=200)
            except Exception:
                pass
                
        st.divider()
        
        if selected_prod_name != "Tutti":
            st.write(f"### ⚙️ Setup Avanzato - {selected_prod_name}")
            
            pezzi = []
            for p in catalogo_componenti:
                if p and p.get("id_Produttori") == prod_id_selezionato:
                    cat_componente = p.get("category_id") if p.get("category_id") is not None else p.get("categoria")
                    if cat_componente is None:
                        pezzi.append(p)
                    elif str(cat_componente) == str(category_id):
                        pezzi.append(p)
                        
            scelte_utente = {}
            model_safe_key = selected_model_name.replace(" ", "_").replace(".", "_")
            
            def helper_filtra_pezzi(campo):
                c_low = campo.lower()
                if "motore" in c_low and "supporto" not in c_low:
                    return [p for p in pezzi if p and p.get("Prodotto") and "motore" in p.get("Prodotto").lower() and "supporto" not in p.get("Prodotto").lower()]
                elif "supporto" in c_low and "assale" not in c_low:
                    return [p for p in pezzi if p and p.get("Prodotto") and "supporto" in p.get("Prodotto").lower()]
                elif "corona" in c_low:
                    return [p for p in pezzi if p and p.get("Prodotto") and "corona" in p.get("Prodotto").lower()]
                elif "pignoni" in c_low or "pignone" in c_low:
                    return [p for p in pezzi if p and p.get("Prodotto") and "pignon" in p.get("Prodotto").lower()]
                elif "telaio" in c_low:
                    return [p for p in pezzi if p and p.get("Prodotto") and "telaio" in p.get("Prodotto").lower()]
                elif "assale" in c_low:
                    return [p for p in pezzi if p and p.get("Prodotto") and "assale" in p.get("Prodotto").lower()]
                elif "cerch" in c_low:
                    return [p for p in pezzi if p and p.get("Prodotto") and "cerch" in p.get("Prodotto").lower()]
                elif "pickup" in c_low:
                    return [p for p in pezzi if p and p.get("Prodotto") and "pickup" in p.get("Prodotto").lower()]
                elif "viti carrozzeria" in c_low or "viti" in c_low:
                    return [p for p in pezzi if p and p.get("Prodotto") and ("viti" in p.get("Prodotto").lower() or "carrozzeria" in p.get("Prodotto").lower())]
                return []

            def render_select_componente(campo, sub_pezzi_list, key_prefix):
                opzioni = []
                for p in sub_pezzi_list:
                    mat = p.get("Materiale")
                    mis = p.get("Misure")
                    parte_mat = str(mat).strip() if mat and str(mat).lower() != "none" else ""
                    parte_mis = str(mis).strip() if mis and str(mis).lower() != "none" else ""
                    str_opt = f"{parte_mat} - {parte_mis}" if parte_mat and parte_mis else (parte_mat or parte_mis)
                    if str_opt:
                        opzioni.append(str_opt)
                        
                saved_val = edit_data.get(campo) if edit_data else None
                def_idx = find_default_index(opzioni, selected_model_name, target_value=saved_val)
                return st.selectbox(
                    campo,
                    opzioni if opzioni else ["Nessuna opzione"],
                    index=def_idx,
                    key=f"{key_prefix}_{campo}_{model_safe_key}"
                )

            if selected_prod_name.lower() == "slot.it":
                col1_slot, col2_slot, col3_slot = st.columns(3)
                with col1_slot:
                    cat_slot_opts = ["Nessuna", "P1", "P2", "Prototipi", "Sport"]
                    def_cat_slot = edit_data.get("Categoria_SlotIt", "Nessuna") if edit_data else "Nessuna"
                    idx_cat_slot = cat_slot_opts.index(def_cat_slot) if def_cat_slot in cat_slot_opts else 0
                    scelte_utente["Categoria_SlotIt"] = st.selectbox(
                        "Categoria",
                        cat_slot_opts,
                        index=idx_cat_slot,
                        key=f"slotit_categoria_{model_safe_key}"
                    )
                with col2_slot:
                    scelte_utente["Peso_Carrozzeria"] = st.text_input(
                        "Peso Carrozzeria",
                        value=str(edit_data.get("Peso_Carrozzeria", "")) if edit_data else "",
                        key=f"peso_carrozzeria_{model_safe_key}"
                    )
                with col3_slot:
                    scelte_utente["Peso_Totale"] = st.text_input(
                        "Peso Totale",
                        value=str(edit_data.get("Peso_Totale", "")) if edit_data else "",
                        key=f"peso_totale_{model_safe_key}"
                    )
                    
                slotit_campi = [
                    "Motore", "Giri Motore", "Telaio", "Supporto Motore",
                    "Corona", "Pignoni", "Assale Anteriore", "Assale Posteriore",
                    "Cerchi Anteriori", "Cerchi Posteriori", "Pickup",
                    "Viti Carrozzeria", "Stopper"
                ]
                
                cols = st.columns(3)
                for idx, campo in enumerate(slotit_campi):
                    with cols[idx % 3]:
                        if campo == "Giri Motore":
                            scelte_utente["Giri_Motore"] = st.text_input(
                                "Giri Motore",
                                value=str(edit_data.get("Giri_Motore", "")) if edit_data else "",
                                key=f"giri_motore_slotit_{model_safe_key}"
                            )
                        elif campo == "Stopper":
                            stopper_opts = ["No", "Sì"]
                            def_stop = edit_data.get("Stopper", "No") if edit_data else "No"
                            idx_stop = stopper_opts.index(def_stop) if def_stop in stopper_opts else 0
                            scelte_utente["Stopper"] = st.selectbox(
                                "Stopper",
                                stopper_opts,
                                index=idx_stop,
                                key=f"slotit_stopper_{model_safe_key}"
                            )
                        else:
                            sub_pezzi = helper_filtra_pezzi(campo)
                            scelte_utente[campo] = render_select_componente(campo, sub_pezzi, "slotit")
                            
                st.write("### 🔩 Sospensioni")
                col_viti, col_tipo_sosp = st.columns(2)
                
                with col_viti:
                    sub_viti_sosp = [p for p in pezzi if p and p.get("Prodotto") and p.get("Prodotto").strip().lower() == "viti metriche sospensioni"]
                    scelte_utente["Viti_Metriche_Sospensioni"] = render_select_componente("Viti_Metriche_Sospensioni", sub_viti_sosp, "slotit_viti")
                    
                with col_tipo_sosp:
                    tipo_sosp_opts = ["Molle", "Magneti"]
                    def_t_sosp = edit_data.get("Tipo_Sospensione", "Molle") if edit_data else "Molle"
                    idx_t_sosp = tipo_sosp_opts.index(def_t_sosp) if def_t_sosp in tipo_sosp_opts else 0
                    tipo_sosp_slotit = st.selectbox(
                        "Tipo Sospensione",
                        tipo_sosp_opts,
                        index=idx_t_sosp,
                        key=f"slotit_tipo_sospensione_{model_safe_key}"
                    )
                    scelte_utente["Tipo_Sospensione"] = tipo_sosp_slotit
                    
                if tipo_sosp_slotit == "Magneti":
                    sub_sosp = [p for p in pezzi if p and p.get("Prodotto") and p.get("Prodotto").strip().lower() == "sospensioni magnetiche"]
                else:
                    sub_sosp = [p for p in pezzi if p and p.get("Prodotto") and p.get("Prodotto").strip().lower() == "sospensioni"]
                    
                scelte_utente["Sospensioni"] = render_select_componente("Sospensioni", sub_sosp, "slotit_scelta_sosp")

            else:
                col_p1, col_p2, _ = st.columns(3)
                with col_p1:
                    scelte_utente["Peso_Carrozzeria"] = st.text_input(
                        "Peso Carrozzeria",
                        value=str(edit_data.get("Peso_Carrozzeria", "")) if edit_data else "",
                        key=f"peso_carrozzeria_{selected_prod_name}_{model_safe_key}"
                    )
                with col_p2:
                    scelte_utente["Peso_Totale"] = st.text_input(
                        "Peso Totale",
                        value=str(edit_data.get("Peso_Totale", "")) if edit_data else "",
                        key=f"peso_totale_{selected_prod_name}_{model_safe_key}"
                    )
                    
                if selected_prod_name.lower() == "nsr":
                    nsr_campi = [
                        "Motore", "Supporto Motore", "Corona", "Giri Motore",
                        "Pignoni", "Telaio", "Assale Anteriore", "Assale Posteriore",
                        "Cerchi Anteriori", "Cerchi Posteriori", "Pickup", "Viti Carrozzeria"
                    ]
                    
                    cols = st.columns(3)
                    for idx, campo in enumerate(nsr_campi):
                        with cols[idx % 3]:
                            if campo == "Giri Motore":
                                scelte_utente["Giri_Motore"] = st.text_input(
                                    "Giri Motore",
                                    value=str(edit_data.get("Giri_Motore", "")) if edit_data else "",
                                    key=f"giri_motore_nsr_{model_safe_key}"
                                )
                            else:
                                sub_pezzi = helper_filtra_pezzi(campo)
                                scelte_utente[campo] = render_select_componente(campo, sub_pezzi, "nsr")
                                
                    st.write("### 🔩 Sospensioni")
                    sosp_nsr_opts = ["No", "Sì"]
                    def_sosp_nsr = edit_data.get("Sospensioni", "No") if edit_data else "No"
                    idx_sosp_nsr = sosp_nsr_opts.index(def_sosp_nsr) if def_sosp_nsr in sosp_nsr_opts else 0
                    sosp_nsr_attive = st.selectbox(
                        "Sospensioni",
                        sosp_nsr_opts,
                        index=idx_sosp_nsr,
                        key=f"nsr_sosp_sino_{model_safe_key}"
                    )
                    scelte_utente["Sospensioni"] = sosp_nsr_attive
                    if sosp_nsr_attive == "Sì":
                        molla_nsr_opts = ["Molle Hard", "Molle Medium", "Molle Soft"]
                        def_molla_nsr = edit_data.get("Tipo_Molla_NSR", "Molle Hard") if edit_data else "Molle Hard"
                        idx_molla_nsr = molla_nsr_opts.index(def_molla_nsr) if def_molla_nsr in molla_nsr_opts else 0
                        scelte_utente["Tipo_Molla_NSR"] = st.selectbox(
                            "Tipo Molla",
                            molla_nsr_opts,
                            index=idx_molla_nsr,
                            key=f"nsr_tipo_molla_{model_safe_key}"
                        )
                        
                elif selected_prod_name.lower() == "thunderslot":
                    thunder_campi = [
                        "Motore", "Supporto Motore", "Corona", "Giri Motore",
                        "Telaio", "Cerchi Anteriori", "Cerchi Posteriori",
                        "Viti Carrozzeria", "Assale"
                    ]
                    
                    cols = st.columns(3)
                    for idx, campo in enumerate(thunder_campi):
                        with cols[idx % 3]:
                            if campo == "Giri Motore":
                                scelte_utente["Giri_Motore"] = st.text_input(
                                    "Giri Motore",
                                    value=str(edit_data.get("Giri_Motore", "")) if edit_data else "",
                                    key=f"giri_motore_thunderslot_{model_safe_key}"
                                )
                            else:
                                sub_pezzi = helper_filtra_pezzi(campo)
                                scelte_utente[campo] = render_select_componente(campo, sub_pezzi, "thunder")
                                
                    st.write("### 🔩 Sospensioni Thunderslot")
                    col_sosp1, col_sosp2, col_sosp3 = st.columns(3)
                    tipi_sospensioni_thunderslot = ["Posteriori", "Laterali", "Anteriori"]
                    
                    for i, tipo_sosp in enumerate(tipi_sospensioni_thunderslot):
                        col_corrente = [col_sosp1, col_sosp2, col_sosp3][i]
                        key_base = tipo_sosp.lower()
                        
                        with col_corrente:
                            st.markdown(f"**Sospensioni {tipo_sosp}**")
                            sosp_t_opts = ["No", "Sì"]
                            def_sosp_t = edit_data.get(f"Sospensioni_{tipo_sosp}", "No") if edit_data else "No"
                            idx_sosp_t = sosp_t_opts.index(def_sosp_t) if def_sosp_t in sosp_t_opts else 0
                            sosp_attive = st.selectbox(
                                "Stato",
                                sosp_t_opts,
                                index=idx_sosp_t,
                                key=f"thunder_sosp_{key_base}_sino_{model_safe_key}"
                            )
                            scelte_utente[f"Sospensioni_{tipo_sosp}"] = sosp_attive
                            
                            if sosp_attive == "Sì":
                                tipo_m_opts = ["Molle", "Spugna"]
                                def_tipo_m = edit_data.get(f"Tipo_Sospensione_{tipo_sosp}", "Molle") if edit_data else "Molle"
                                idx_tipo_m = tipo_m_opts.index(def_tipo_m) if def_tipo_m in tipo_m_opts else 0
                                tipo_materiale_sosp = st.selectbox(
                                    "Tipo",
                                    tipo_m_opts,
                                    index=idx_tipo_m,
                                    key=f"thunder_sosp_{key_base}_tipo_{model_safe_key}"
                                )
                                scelte_utente[f"Tipo_Sospensione_{tipo_sosp}"] = tipo_materiale_sosp
                                
                                if tipo_materiale_sosp == "Molle":
                                    dur_opts = ["Molle morbide", "Molle medie", "Molle dure"]
                                    def_dur = edit_data.get(f"Durezza_Molla_{tipo_sosp}", "Molle morbide") if edit_data else "Molle morbide"
                                    idx_dur = dur_opts.index(def_dur) if def_dur in dur_opts else 0
                                    durezza_molla = st.selectbox(
                                        "Durezza",
                                        dur_opts,
                                        index=idx_dur,
                                        key=f"thunder_sosp_{key_base}_durezza_{model_safe_key}"
                                    )
                                    scelte_utente[f"Durezza_Molla_{tipo_sosp}"] = durezza_molla

                elif selected_prod_name.lower() == "scaleauto":
                    scaleauto_campi = [
                        "Motore", "Supporto Motore", "Corona", "Giri Motore",
                        "Pignoni", "Telaio", "Assale Anteriore", "Assale Posteriore",
                        "Cerchi Anteriori", "Cerchi Posteriori", "Pickup", "Viti Carrozzeria"
                    ]
                    
                    cols = st.columns(3)
                    for idx, campo in enumerate(scaleauto_campi):
                        with cols[idx % 3]:
                            if campo == "Giri Motore":
                                scelte_utente["Giri_Motore"] = st.text_input(
                                    "Giri Motore",
                                    value=str(edit_data.get("Giri_Motore", "")) if edit_data else "",
                                    key=f"giri_motore_scaleauto_{model_safe_key}"
                                )
                            else:
                                sub_pezzi = helper_filtra_pezzi(campo)
                                scelte_utente[campo] = render_select_componente(campo, sub_pezzi, "scaleauto")
                                
                    st.write("### 🔩 Sospensioni Scaleauto")
                    sosp_sc_opts = ["No", "Sì"]
                    def_sosp_sc = edit_data.get("Sospensioni", "No") if edit_data else "No"
                    idx_sosp_sc = sosp_sc_opts.index(def_sosp_sc) if def_sosp_sc in sosp_sc_opts else 0
                    sosp_sc_attive = st.selectbox(
                        "Sospensioni",
                        sosp_sc_opts,
                        index=idx_sosp_sc,
                        key=f"scaleauto_sosp_sino_{model_safe_key}"
                    )
                    scelte_utente["Sospensioni"] = sosp_sc_attive
                    if sosp_sc_attive == "Sì":
                        tipo_sosp_sc_opts = ["Molle", "Gomma"]
                        def_t_sosp_sc = edit_data.get("Tipo_Sospensione_Scaleauto", "Molle") if edit_data else "Molle"
                        idx_t_sosp_sc = tipo_sosp_sc_opts.index(def_t_sosp_sc) if def_t_sosp_sc in tipo_sosp_sc_opts else 0
                        scelte_utente["Tipo_Sospensione_Scaleauto"] = st.selectbox(
                            "Tipo Sospensione",
                            tipo_sosp_sc_opts,
                            index=idx_t_sosp_sc,
                            key=f"scaleauto_tipo_sosp_{model_safe_key}"
                        )

        st.divider()
        st.write("### 📝 Note e Osservazioni sul Setup")
        note_setup = st.text_area(
            "Note",
            value=str(edit_data.get("Note", "")) if edit_data else "",
            key=f"note_setup_{model_safe_key}"
        )
        scelte_utente["Note"] = note_setup
        scelte_utente["foto_personalizzata_url"] = foto_personalizzata_finale
        
        col_save1, col_save2 = st.columns(2)
        with col_save1:
            btn_label = "💾 Salva Modifiche" if st.session_state.modifying_config_id else "💾 Salva Configurazione nel Garage"
            if st.button(btn_label, type="primary", use_container_width=True):
                if not st.session_state.get("user_email_garage"):
                    email_input = st.text_input("Inserisci la tua email per salvare il setup nel garage:", key="email_save_input")
                    if email_input:
                        st.session_state["user_email_garage"] = email_input
                        st.rerun()
                    else:
                        st.warning("Inserisci un'email valida per procedere al salvataggio.")
                else:
                    email_user = st.session_state["user_email_garage"]
                    payload = {
                        "user_email": email_user,
                        "model_name": selected_model_name,
                        "config_name": st.session_state.get("modifying_config_name", f"Setup {selected_model_name}"),
                        "dettagli": scelte_utente
                    }
                    if st.session_state.modifying_config_id:
                        try:
                            supabase.table("Garage").update(payload).eq("id", st.session_state.modifying_config_id).execute()
                            st.success("Configurazione aggiornata con successo!")
                            st.session_state.modifying_config_id = None
                            st.session_state.modifying_data = None
                            st.session_state.modifying_config_name = ""
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Errore durante l'aggiornamento: {e}")
                    else:
                        try:
                            supabase.table("Garage").insert(payload).execute()
                            st.success("Configurazione salvata nel tuo garage con successo!")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Errore durante il salvataggio: {e}")
                            
        with col_save2:
            pdf_bytes = generate_pdf(
                st.session_state.get("modifying_config_name", f"Setup_{selected_model_name}"),
                selected_model_name,
                scelte_utente,
                foto_personalizzata_finale or default_foto_db
            )
            st.download_button(
                label="📥 Scarica Scheda Tecnica PDF",
                data=pdf_bytes,
                file_name=f"setup_{selected_model_name.replace(' ', '_')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
    else:
        st.info("Seleziona un modello specifico per visualizzare e configurare il setup.")

elif st.session_state.active_tab == "🚗 Il Mio Garage":
    st.subheader("🚗 Il Mio Garage - Configurazioni Salvate")
    email_garage_view = st.text_input("Inserisci la tua email per visualizzare i tuoi setup salvati:", key="email_garage_view_input")
    if email_garage_view:
        try:
            res_garage = supabase.table("Garage").select("*").eq("user_email", email_garage_view).execute()
            saved_items = res_garage.data if res_garage else []
            if not saved_items:
                st.info("Nessuna configurazione trovata per questa email.")
            else:
                for item in saved_items:
                    with st.expander(f"🏎️ {item.get('config_name', 'Setup')} - Modello: {item.get('model_name', 'N/D')}"):
                        st.write(f"**Email**: {item.get('user_email')}")
                        dettagli_item = item.get("dettagli", {})
                        if isinstance(dettagli_item, str):
                            try:
                                dettagli_item = ast.literal_eval(dettagli_item)
                            except Exception:
                                dettagli_item = {}
                                
                        foto_item = dettagli_item.get("foto_personalizzata_url")
                        if foto_item:
                            try:
                                st.image(foto_item, width=200)
                            except Exception:
                                pass
                                
                        st.json(dettagli_item)
                        
                        col_g1, col_g2, col_g3 = st.columns(3)
                        with col_g1:
                            if st.button("✏️ Modifica Setup", key=f"mod_btn_{item.get('id')}"):
                                st.session_state.modifying_config_id = item.get("id")
                                st.session_state.modifying_data = dettagli_item
                                st.session_state.modifying_config_name = item.get("config_name")
                                st.session_state.modifying_model_name = item.get("model_name")
                                st.session_state.active_tab = "📋 Visualizza Modelli"
                                st.rerun()
                        with col_g2:
                            pdf_item_bytes = generate_pdf(
                                item.get("config_name", "Setup"),
                                item.get("model_name", "Modello"),
                                dettagli_item,
                                foto_item
                            )
                            st.download_button(
                                label="📥 PDF",
                                data=pdf_item_bytes,
                                file_name=f"setup_{item.get('id')}.pdf",
                                mime="application/pdf",
                                key=f"pdf_btn_{item.get('id')}"
                            )
                        with col_g3:
                            if st.button("🗑️ Elimina", key=f"del_btn_{item.get('id')}"):
                                try:
                                    supabase.table("Garage").delete().eq("id", item.get("id")).execute()
                                    st.success("Configurazione eliminata.")
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Errore eliminazione: {e}")
        except Exception as e:
            st.error(f"Errore nel recupero dei dati dal garage: {e}")

elif st.session_state.active_tab == "🎛️ Il Mio Pulsante":
    st.subheader("🎛️ Il Mio Pulsante - Gestione Configurazioni Controller")
    email_pulsante = st.text_input("Inserisci la tua email per gestire i setup del pulsante:", key="email_pulsante_input")
    if email_pulsante:
        try:
            res_p = supabase.table("Pulsanti").select("*").eq("user_email", email_pulsante).execute()
            pulsante_items = res_p.data if res_p else []
            if not pulsante_items:
                st.info("Nessuna configurazione pulsante trovata.")
            else:
                for p_item in pulsante_items:
                    st.write(f"Configurazione Pulsante ID: {p_item.get('id')}")
                    st.json(p_item)
        except Exception as e:
            st.warning(f"Tabella Pulsanti non ancora attiva o vuota: {e}")
            
    st.markdown("### ➕ Crea o Modifica Configurazione Pulsante")
    nome_pulsante_config = st.text_input("Nome Configurazione Pulsante", key="nome_pulsante_input")
    sensibilita = st.slider("Sensibilità", 1, 10, 5, key="slider_sensibilita")
    frenata = st.slider("Frenata", 1, 10, 5, key="slider_frenata")
    
    if st.button("💾 Salva Configurazione Pulsante"):
        if email_pulsante:
            payload_p = {
                "user_email": email_pulsante,
                "nome_config": nome_pulsante_config,
                "sensibilita": sensibilita,
                "frenata": frenata
            }
            try:
                supabase.table("Pulsanti").insert(payload_p).execute()
                st.success("Configurazione pulsante salvata con successo!")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Errore salvataggio pulsante: {e}")
        else:
            st.warning("Inserisci prima l'email.")

elif st.session_state.active_tab == "➕ Carica Modello":
    st.subheader("➕ Carica un Nuovo Modello nel Database")
    with st.form("form_carica_modello"):
        nuovo_produttore = st.selectbox("Produttore", [p.get("name") for p in produttori if p and p.get("name")])
        nuovo_nome_modello = st.text_input("Nome Nuovo Modello")
        nuova_categoria = st.text_input("Categoria (ID o Nome)")
        nuova_foto_url = st.text_input("URL Foto di Default (Opzionale)")
        
        submit_modello = st.form_submit_button("Carica Modello")
        if submit_modello:
            if nuovo_nome_modello:
                try:
                    p_obj_target = next((p for p in produttori if p.get("name") == nuovo_produttore), None)
                    p_id_target = p_obj_target.get("id") if p_obj_target else None
                    
                    payload_m = {
                        "name": nuovo_nome_modello,
                        "foto_url": nuova_foto_url
                    }
                    supabase.table("MODELLI").insert(payload_m).execute()
                    st.success(f"Modello '{nuovo_nome_modello}' caricato con successo!")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Errore durante il caricamento del modello: {e}")
            else:
                st.warning("Inserisci il nome del modello.")
