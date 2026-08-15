import ast
import os
import time
import tempfile
import traceback
from fpdf import FPDF
import requests
import streamlit as st
from supabase import create_client

LOGO_PATH = "logo.png"
APP_ICON_PATH = "pwa-icon-192.png"

# --- CONFIGURAZIONE PAGINA (PRIMISSIMA ISTRUZIONE STREAMLIT) ---
st.set_page_config(page_title="SlotGarage", page_icon=APP_ICON_PATH, layout="wide")

# --- CONFIGURAZIONE SUPABASE & SICUREZZA ---
try:
    SUPABASE_URL = st.secrets["supabase"]["url"]
    SUPABASE_KEY = st.secrets["supabase"]["key"]
except Exception:
    SUPABASE_URL = "https://rmfaphfksvcyynfrrbsy.supabase.co"
    SUPABASE_KEY = "sb_secret_MQc2t0J_yWMBIoh4kZNPeA_ztE8RE9e"


@st.cache_resource
def init_connection():
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        st.error(f"Errore di connessione a Supabase: {e}")
        return None


supabase = init_connection()

# --- INIEZIONE AVANZATA META TAG PER PWA & MOBILE ---
st.html(
    """
    <script>
        const targetDoc = (window.parent && window.parent.document) ? window.parent.document : document;
        const docHead = targetDoc.head || targetDoc.getElementsByTagName('head')[0];

        if (docHead) {
            const existingLinks = docHead.querySelectorAll('link[rel="apple-touch-icon"], link[rel="manifest"]');
            existingLinks.forEach(el => el.remove());

            const manifestLink = targetDoc.createElement('link');
            manifestLink.rel = 'manifest';
            manifestLink.href = './manifest.json';
            docHead.appendChild(manifestLink);

            const appleIcon = targetDoc.createElement('link');
            appleIcon.rel = 'apple-touch-icon';
            appleIcon.href = './pwa-icon-180.png';
            docHead.appendChild(appleIcon);

            const metaName = targetDoc.createElement('meta');
            metaName.name = 'apple-mobile-web-app-title';
            metaName.content = 'SlotGarage';
            docHead.appendChild(metaName);

            const metaCapable = targetDoc.createElement('meta');
            metaCapable.name = 'apple-mobile-web-app-capable';
            metaCapable.content = 'yes';
            docHead.appendChild(metaCapable);
        }
    </script>
    """
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
        "<h1 style='margin-top: 25px; font-size: 4.2rem; margin-bottom:"
        " 0px;'>SlotGarage</h1><p style='color: #FFD700; font-size: 1.3rem;"
        " margin-top: 0px;'>Creato da Emanuele Palena</p>",
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
    st.warning(
        "Connessione al cloud in corso o database temporaneamente in standby..."
    )
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

prod_options = {
    p.get("name"): p.get("id")
    for p in produttori
    if p and p.get("name") and p.get("id")
}

default_prod_idx = 0
default_cat_idx = 0
default_mod_idx = 0

pre_selected_prod = "Tutti"
pre_selected_cat = "Tutte"
pre_selected_mod = "Tutti"

if st.session_state.modifying_config_id and st.session_state.get(
    "modifying_model_name"
):
    mod_name_target = st.session_state.get("modifying_model_name")
    m_obj = next(
        (m for m in modelli if m and m.get("name") == mod_name_target), None
    )
    if m_obj:
        pre_selected_mod = m_obj.get("name")
        cat_id_target = m_obj.get("category_id")
        c_obj = next(
            (c for c in categorie if c and c.get("id") == cat_id_target), None
        )
        if c_obj:
            pre_selected_cat = c_obj.get("name")
            prod_id_target = c_obj.get("brand_it")
            p_obj = next(
                (p for p in produttori if p and p.get("id") == prod_id_target), None
            )
            if p_obj:
                pre_selected_prod = p_obj.get("name")

col_producer_filter, col_category_filter, col_model_filter = st.columns(3)

prod_names_list = ["Tutti"] + list(prod_options.keys())
if pre_selected_prod in prod_names_list:
    default_prod_idx = prod_names_list.index(pre_selected_prod)

with col_producer_filter:
    selected_prod_name = st.selectbox(
        "Seleziona Produttore", prod_names_list, index=default_prod_idx
    )

if selected_prod_name != "Tutti":
    prod_id = prod_options[selected_prod_name]
    cat_options = {
        c.get("name"): c.get("id")
        for c in categorie
        if c and c.get("brand_it") == prod_id
    }
else:
    cat_options = {
        c.get("name"): c.get("id")
        for c in categorie
        if c and c.get("name") and c.get("id")
    }

cat_names_list = ["Tutte"] + list(cat_options.keys())
if pre_selected_cat in cat_names_list:
    default_cat_idx = cat_names_list.index(pre_selected_cat)

with col_category_filter:
    selected_cat_name = st.selectbox(
        "Seleziona Categoria", cat_names_list, index=default_cat_idx
    )

if selected_cat_name != "Tutte":
    cat_id = cat_options[selected_cat_name]
    mod_list = [
        m.get("name")
        for m in modelli
        if m and m.get("category_id") == cat_id and m.get("name")
    ]
else:
    mod_list = [m.get("name") for m in modelli if m and m.get("name")]

mod_names_list = ["Tutti"] + mod_list
if pre_selected_mod in mod_names_list:
    default_mod_idx = mod_names_list.index(pre_selected_mod)

with col_model_filter:
    selected_model_name = st.selectbox(
        "Seleziona Modello", mod_names_list, index=default_mod_idx
    )

st.divider()

# --- MENU DI NAVIGAZIONE GESTITO VIA STATO ---
tabs_list = [
    "📋 Visualizza Modelli",
    "🚗 Il Mio Garage",
    "🎛️ Il Mio Pulsante",
    "➕ Carica Modello",
]
selected_tab = st.radio(
    "Navigazione",
    tabs_list,
    index=(
        tabs_list.index(st.session_state.active_tab)
        if st.session_state.active_tab in tabs_list
        else 0
    ),
    horizontal=True,
    label_visibility="collapsed",
)
st.session_state.active_tab = selected_tab
st.divider()


def find_default_index(opzioni: list, model_name: str, target_value=None) -> int:
    """Trova l'indice di default in una lista di opzioni basato su model_name o target_value."""
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
    """Carica un file immagine su Supabase storage e ritorna l'URL pubblico.
    
    Args:
        uploaded_file: File object da Streamlit file_uploader
    
    Returns:
        str: URL pubblico dell'immagine, None se errore
    """
    if uploaded_file is None:
        return None
    try:
        file_ext = uploaded_file.name.split(".")[-1]
        file_name = f"car_{int(time.time())}_{os.urandom(2).hex()}.{file_ext}"
        file_bytes = uploaded_file.getvalue()

        supabase.storage.from_("immagini-garage").upload(
            path=file_name,
            file=file_bytes,
            file_options={"content-type": uploaded_file.type},
        )

        public_url_res = supabase.storage.from_("immagini-garage").get_public_url(
            file_name
        )
        return public_url_res
    except Exception as e:
        st.error(f"Errore durante il caricamento dell'immagine nel cloud: {e}")
        return None


def generate_pdf(config_name, modello_nome, dettagli, foto_url=None):
    """Genera un PDF con scheda tecnica del modello auto slot car.
    
    Args:
        config_name (str): Nome della configurazione
        modello_nome (str): Nome del modello auto
        dettagli (dict): Dizionario con dettagli tecnici (peso, motore, ecc.)
        foto_url (str, optional): URL foto modello da includere nel PDF
    
    Returns:
        bytes: PDF generato in formato bytes
    """
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()

    bg_dark = (30, 32, 36)
    accent_bar = (220, 50, 50)
    text_dark = (40, 40, 40)
    text_light = (255, 255, 255)

    pdf.set_fill_color(250, 252, 255)
    pdf.rect(0, 0, 297, 210, "F")

    pdf.set_fill_color(*bg_dark)
    pdf.rect(0, 0, 297, 16, "F")
    pdf.set_fill_color(*accent_bar)
    pdf.rect(0, 16, 297, 2, "F")

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
                    pdf.image(img_file_obj.name, x=left_x + 2, y=current_y, w=left_w - 4)
                    current_y += 48
            else:
                if os.path.exists(foto_url):
                    pdf.image(foto_url, x=left_x + 2, y=current_y, w=left_w - 4)
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

    pesi_motore_Keys = [
        "Peso_Carrozzeria",
        "Peso_Totale",
        "Giri_Motore",
        "Motore",
        "Supporto Motore",
        "Corona",
        "Pignoni",
    ]

    dettagli_filtrati = {}
    for k, v in dettagli.items():
        if k.lower() == "note" or k.lower() == "foto_personalizzata_url":
            continue
        if k in ["Distanziali_Anteriori", "Distanziali_Posteriori"]:
            continue
        if k == "Distanziali_Pickup":
            val_misura = dettagli.get("Distanziale_Pickup", "")
            if (
                str(v).lower() == "sì"
                and val_misura
                and str(val_misura).lower() != "nessun distanziale disponibile"
            ):
                dettagli_filtrati["Distanziale_Pickup"] = val_misura
            else:
                dettagli_filtrati["Distanziale_Pickup"] = v
            continue
        if k == "Distanziale_Pickup":
            continue
        dettagli_filtrati[k] = v

    left_items = {
        k: v
        for k, v in dettagli_filtrati.items()
        if any(pk in k for pk in pesi_motore_Keys)
    }
    right_items = {
        k: v for k, v in dettagli_filtrati.items() if k not in left_items
    }

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
    h_col1 = draw_tech_section(
        col1_x,
        box_start_y,
        col_w,
        "PROPULSIONE & PESI",
        left_items if left_items else {"Info": "Nessun dato"},
    )
    h_col2 = draw_tech_section(
        col2_x,
        box_start_y,
        col_w,
        "Assetto",
        right_items if right_items else dettagli_filtrati,
    )

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

    return pdf.output(dest="S").encode("latin-1", "replace")


# --- GESTIONE SEZIONI (TAB) ---

if st.session_state.active_tab == "📋 Visualizza Modelli":
    if selected_model_name != "Tutti":
        modello_selezionato = next(
            (m for m in modelli if m and m.get("name") == selected_model_name), None
        )
        modello_id = modello_selezionato.get("id") if modello_selezionato else None
        category_id = (
            cat_options.get(selected_cat_name)
            if selected_cat_name in cat_options
            else None
        )
        prod_id_selezionato = (
            prod_options.get(selected_prod_name)
            if selected_prod_name in prod_options
            else None
        )

        edit_data = (
            st.session_state.modifying_data
            if st.session_state.modifying_config_id
            else {}
        )

        if st.session_state.modifying_config_id:
            st.warning(
                f"⚠️ Stai modificando la configurazione esistente: "
                f"**{st.session_state.get('modifying_config_name', '')}**."
                " Modifica i parametri desiderati e clicca su 'Salva Modifiche' in"
                " fondo alla pagina per confermare."
            )

        st.subheader(f"Configurazione: {selected_model_name}")

        default_foto_db = (
            modello_selezionato.get("foto_url") if modello_selezionato else None
        )
        if default_foto_db:
            try:
                st.image(
                    default_foto_db,
                    caption=f"Foto di default: {selected_model_name}",
                    width=250,
                )
            except Exception:
                pass

        st.markdown("### 📸 Foto Personalizzata del Tuo Modello (Opzionale)")
        col_photo_upload, col_photo_url = st.columns(2)
        with col_photo_upload:
            file_foto_pers = st.file_uploader(
                "Carica immagine dal dispositivo",
                type=["jpg", "jpeg", "png"],
                key="file_foto_pers_setup",
            )
        with col_photo_url:
            url_foto_pers = st.text_input(
                "O inserisci URL immagine personalizzata",
                value=(
                    str(edit_data.get("foto_personalizzata_url", ""))
                    if edit_data and "foto_personalizzata_url" in edit_data
                    else ""
                ),
                key="url_foto_pers_setup",
            )

        foto_personalizzata_finale = url_foto_pers
        if file_foto_pers is not None:
            with st.spinner("Caricamento immagine nel cloud in corso..."):
                uploaded_cloud_url = upload_image_to_supabase(file_foto_pers)
                if uploaded_cloud_url:
                    foto_personalizzata_finale = uploaded_cloud_url
                    st.success("Immagine caricata con successo nel cloud!")
        elif (
            not url_foto_pers
            and edit_data
            and "foto_personalizzata_url" in edit_data
        ):
            foto_personalizzata_finale = edit_data.get("foto_personalizzata_url")

        if foto_personalizzata_finale:
            try:
                st.image(
                    foto_personalizzata_finale,
                    caption="Anteprima Foto Personalizzata",
                    width=200,
                )
            except Exception:
                pass

        st.divider()

        if selected_prod_name != "Tutti":
            st.write(f"### ⚙️ Setup Avanzato - {selected_prod_name}")

            pezzi = []
            for p in catalogo_componenti:
                if p and p.get("id_Produttori") == prod_id_selezionato:
                    cat_componente = (
                        p.get("category_id")
                        if p.get("category_id") is not None
                        else p.get("categoria")
                    )
                    if cat_componente is None:
                        pezzi.append(p)
                    elif str(cat_componente) == str(category_id):
                        pezzi.append(p)

            scelte_utente = {}
            model_safe_key = selected_model_name.replace(" ", "_").replace(".", "_")

            def helper_filtra_pezzi(campo: str) -> list:
                """Filtra pezzi in base al campo richiesto. Utilizza keywords mapping per evitare ripetizioni."""
                # Mapping campo -> keywords da cercare in "Prodotto"
                keywords_mapping = {
                    "motore": (["motore"], ["supporto"]),  # include, exclude
                    "supporto motore": (["supporto"], ["assale"]),
                    "corona": (["corona"], []),
                    "pignoni": (["pignon"], []),
                    "pignone": (["pignon"], []),
                    "telaio": (["telaio"], []),
                    "assale": (["assale"], []),
                    "cerchi": (["cerch"], []),
                    "cerchi anteriori": (["cerch"], []),
                    "cerchi posteriori": (["cerch"], []),
                    "pickup": (["pickup"], []),
                    "viti": (["viti", "carrozzeria"], []),
                    "viti carrozzeria": (["viti", "carrozzeria"], []),
                }
                
                c_low = campo.lower()
                includes, excludes = keywords_mapping.get(c_low, ([], []))
                
                if not includes:
                    return []
                
                def matches_prodotto(prodotto_str: str) -> bool:
                    """Verifica se prodotto contiene i keywords include e nessuno dei exclude."""
                    prod_lower = prodotto_str.lower()
                    return all(kw in prod_lower for kw in includes) and not any(kw in prod_lower for kw in excludes)
                
                return [
                    p for p in pezzi
                    if p and p.get("Prodotto") and matches_prodotto(p.get("Prodotto"))
                ]

            def render_select_componente(campo, sub_pezzi_list, key_prefix):
                opzioni = []
                for p in sub_pezzi_list:
                    mat = p.get("Materiale")
                    mis = p.get("Misure")
                    parte_mat = (
                        str(mat).strip() if mat and str(mat).lower() != "none" else ""
                    )
                    parte_mis = (
                        str(mis).strip() if mis and str(mis).lower() != "none" else ""
                    )
                    str_opt = (
                        f"{parte_mat} - {parte_mis}"
                        if parte_mat and parte_mis
                        else (parte_mat or parte_mis)
                    )
                    if str_opt:
                        opzioni.append(str_opt)

                saved_val = edit_data.get(campo) if edit_data else None
                def_idx = find_default_index(
                    opzioni, selected_model_name, target_value=saved_val
                )
                return st.selectbox(
                    campo,
                    opzioni if opzioni else ["Nessuna opzione"],
                    index=def_idx,
                    key=f"{key_prefix}_{campo}_{model_safe_key}",
                )

            if selected_prod_name.lower() == "slot.it":
                col_category, col_body_weight, col_total_weight = st.columns(3)
                with col_category:
                    cat_slot_opts = ["Nessuna", "P1", "P2", "Prototipi", "Sport"]
                    def_cat_slot = (
                        edit_data.get("Categoria_SlotIt", "Nessuna")
                        if edit_data
                        else "Nessuna"
                    )
                    idx_cat_slot = (
                        cat_slot_opts.index(def_cat_slot)
                        if def_cat_slot in cat_slot_opts
                        else 0
                    )
                    scelte_utente["Categoria_SlotIt"] = st.selectbox(
                        "Categoria",
                        cat_slot_opts,
                        index=idx_cat_slot,
                        key=f"slotit_categoria_{model_safe_key}",
                    )
                with col_body_weight:
                    scelte_utente["Peso_Carrozzeria"] = st.text_input(
                        "Peso Carrozzeria",
                        value=(
                            str(edit_data.get("Peso_Carrozzeria", "")) if edit_data else ""
                        ),
                        key=f"peso_carrozzeria_{model_safe_key}",
                    )
                with col_total_weight:
                    scelte_utente["Peso_Totale"] = st.text_input(
                        "Peso Totale",
                        value=str(edit_data.get("Peso_Totale", "")) if edit_data else "",
                        key=f"peso_totale_{model_safe_key}",
                    )

                slotit_campi = [
                    "Motore",
                    "Giri Motore",
                    "Telaio",
                    "Supporto Motore",
                    "Corona",
                    "Pignoni",
                    "Assale Anteriore",
                    "Assale Posteriore",
                    "Cerchi Anteriori",
                    "Cerchi Posteriori",
                    "Pickup",
                    "Viti Carrozzeria",
                    "Stopper",
                ]

                cols = st.columns(3)
                for idx, campo in enumerate(slotit_campi):
                    with cols[idx % 3]:
                        if campo == "Giri Motore":
                            scelte_utente["Giri_Motore"] = st.text_input(
                                "Giri Motore",
                                value=(
                                    str(edit_data.get("Giri_Motore", "")) if edit_data else ""
                                ),
                                key=f"giri_motore_slotit_{model_safe_key}",
                            )
                        elif campo == "Stopper":
                            stopper_opts = ["No", "Sì"]
                            def_stop = edit_data.get("Stopper", "No") if edit_data else "No"
                            idx_stop = (
                                stopper_opts.index(def_stop)
                                if def_stop in stopper_opts
                                else 0
                            )
                            scelte_utente["Stopper"] = st.selectbox(
                                "Stopper",
                                stopper_opts,
                                index=idx_stop,
                                key=f"slotit_stopper_{model_safe_key}",
                            )
                        else:
                            sub_pezzi = helper_filtra_pezzi(campo)
                            scelte_utente[campo] = render_select_componente(
                                campo, sub_pezzi, "slotit"
                            )

                st.write("### 🔩 Sospensioni")
                col_viti, col_tipo_sosp = st.columns(2)

                with col_viti:
                    sub_viti_sosp = [
                        p
                        for p in pezzi
                        if p
                        and p.get("Prodotto")
                        and p.get("Prodotto").strip().lower()
                        == "viti metriche sospensioni"
                    ]
                    scelte_utente["Viti_Metriche_Sospensioni"] = render_select_componente(
                        "Viti_Metriche_Sospensioni", sub_viti_sosp, "slotit_viti"
                    )

                with col_tipo_sosp:
                    tipo_sosp_opts = ["Molle", "Magneti"]
                    def_t_sosp = (
                        edit_data.get("Tipo_Sospensione", "Molle") if edit_data else "Molle"
                    )
                    idx_t_sosp = (
                        tipo_sosp_opts.index(def_t_sosp)
                        if def_t_sosp in tipo_sosp_opts
                        else 0
                    )
                    tipo_sosp_slotit = st.selectbox(
                        "Tipo Sospensione",
                        tipo_sosp_opts,
                        index=idx_t_sosp,
                        key=f"slotit_tipo_sospensione_{model_safe_key}",
                    )
                    scelte_utente["Tipo_Sospensione"] = tipo_sosp_slotit

                if tipo_sosp_slotit == "Magneti":
                    sub_sosp = [
                        p
                        for p in pezzi
                        if p
                        and p.get("Prodotto")
                        and p.get("Prodotto").strip().lower()
                        == "sospensioni magnetiche"
                    ]
                else:
                    sub_sosp = [
                        p
                        for p in pezzi
                        if p
                        and p.get("Prodotto")
                        and p.get("Prodotto").strip().lower() == "sospensioni"
                    ]

                scelte_utente["Sospensioni"] = render_select_componente(
                    "Sospensioni", sub_sosp, "slotit_scelta_sosp"
                )

            else:
                col_body_weight, col_total_weight, _ = st.columns(3)
                with col_body_weight:
                    scelte_utente["Peso_Carrozzeria"] = st.text_input(
                        "Peso Carrozzeria",
                        value=(
                            str(edit_data.get("Peso_Carrozzeria", "")) if edit_data else ""
                        ),
                        key=f"peso_carrozzeria_{selected_prod_name}_{model_safe_key}",
                    )
                with col_total_weight:
                    scelte_utente["Peso_Totale"] = st.text_input(
                        "Peso Totale",
                        value=str(edit_data.get("Peso_Totale", "")) if edit_data else "",
                        key=f"peso_totale_{selected_prod_name}_{model_safe_key}",
                    )

                if selected_prod_name.lower() == "nsr":
                    nsr_campi = [
                        "Motore",
                        "Supporto Motore",
                        "Corona",
                        "Giri Motore",
                        "Pignoni",
                        "Telaio",
                        "Assale Anteriore",
                        "Assale Posteriore",
                        "Cerchi Anteriori",
                        "Cerchi Posteriori",
                        "Pickup",
                        "Viti Carrozzeria",
                    ]

                    cols = st.columns(3)
                    for idx, campo in enumerate(nsr_campi):
                        with cols[idx % 3]:
                            if campo == "Giri Motore":
                                scelte_utente["Giri_Motore"] = st.text_input(
                                    "Giri Motore",
                                    value=(
                                        str(edit_data.get("Giri_Motore", "")) if edit_data else ""
                                    ),
                                    key=f"giri_motore_nsr_{model_safe_key}",
                                )
                            else:
                                sub_pezzi = helper_filtra_pezzi(campo)
                                scelte_utente[campo] = render_select_componente(
                                    campo, sub_pezzi, "nsr"
                                )

                    st.write("### 🔩 Sospensioni")
                    sosp_nsr_opts = ["No", "Sì"]
                    def_sosp_nsr = (
                        edit_data.get("Sospensioni", "No") if edit_data else "No"
                    )
                    idx_sosp_nsr = (
                        sosp_nsr_opts.index(def_sosp_nsr)
                        if def_sosp_nsr in sosp_nsr_opts
                        else 0
                    )
                    sosp_nsr_attive = st.selectbox(
                        "Sospensioni",
                        sosp_nsr_opts,
                        index=idx_sosp_nsr,
                        key=f"nsr_sosp_sino_{model_safe_key}",
                    )
                    scelte_utente["Sospensioni"] = sosp_nsr_attive
                    if sosp_nsr_attive == "Sì":
                        molla_nsr_opts = ["Molle Hard", "Molle Medium", "Molle Soft"]
                        def_molla_nsr = (
                            edit_data.get("Tipo_Molla_NSR", "Molle Hard")
                            if edit_data
                            else "Molle Hard"
                        )
                        idx_molla_nsr = (
                            molla_nsr_opts.index(def_molla_nsr)
                            if def_molla_nsr in molla_nsr_opts
                            else 0
                        )
                        scelte_utente["Tipo_Molla_NSR"] = st.selectbox(
                            "Tipo Molla",
                            molla_nsr_opts,
                            index=idx_molla_nsr,
                            key=f"nsr_tipo_molla_{model_safe_key}",
                        )

                elif selected_prod_name.lower() == "thunderslot":
                    thunder_campi = [
                        "Motore",
                        "Supporto Motore",
                        "Corona",
                        "Giri Motore",
                        "Telaio",
                        "Cerchi Anteriori",
                        "Cerchi Posteriori",
                        "Viti Carrozzeria",
                        "Assale",
                    ]

                    cols = st.columns(3)
                    for idx, campo in enumerate(thunder_campi):
                        with cols[idx % 3]:
                            if campo == "Giri Motore":
                                scelte_utente["Giri_Motore"] = st.text_input(
                                    "Giri Motore",
                                    value=(
                                        str(edit_data.get("Giri_Motore", "")) if edit_data else ""
                                    ),
                                    key=f"giri_motore_thunderslot_{model_safe_key}",
                                )
                            else:
                                sub_pezzi = helper_filtra_pezzi(campo)
                                scelte_utente[campo] = render_select_componente(
                                    campo, sub_pezzi, "thunder"
                                )

                    st.write("### 🔩 Sospensioni Thunderslot")
                    col_suspension_rear, col_suspension_side, col_suspension_front = st.columns(3)
                    tipi_sospensioni_thunderslot = ["Posteriori", "Laterali", "Anteriori"]

                    for i, tipo_sosp in enumerate(tipi_sospensioni_thunderslot):
                        col_corrente = [col_suspension_rear, col_suspension_side, col_suspension_front][i]
                        key_base = tipo_sosp.lower()

                        with col_corrente:
                            st.markdown(f"**Sospensioni {tipo_sosp}**")
                            sosp_t_opts = ["No", "Sì"]
                            def_sosp_t = (
                                edit_data.get(f"Sospensioni_{tipo_sosp}", "No")
                                if edit_data
                                else "No"
                            )
                            idx_sosp_t = (
                                sosp_t_opts.index(def_sosp_t)
                                if def_sosp_t in sosp_t_opts
                                else 0
                            )
                            sosp_attive = st.selectbox(
                                "Stato",
                                sosp_t_opts,
                                index=idx_sosp_t,
                                key=f"thunder_sosp_{key_base}_sino_{model_safe_key}",
                            )
                            scelte_utente[f"Sospensioni_{tipo_sosp}"] = sosp_attive

                            if sosp_attive == "Sì":
                                tipo_m_opts = ["Molle", "Spugna"]
                                def_tipo_m = (
                                    edit_data.get(f"Tipo_Sospensione_{tipo_sosp}", "Molle")
                                    if edit_data
                                    else "Molle"
                                )
                                idx_tipo_m = (
                                    tipo_m_opts.index(def_tipo_m)
                                    if def_tipo_m in tipo_m_opts
                                    else 0
                                )
                                tipo_materiale_sosp = st.selectbox(
                                    "Tipo",
                                    tipo_m_opts,
                                    index=idx_tipo_m,
                                    key=f"thunder_sosp_{key_base}_tipo_{model_safe_key}",
                                )
                                scelte_utente[f"Tipo_Sospensione_{tipo_sosp}"] = (
                                    tipo_materiale_sosp
                                )

                                if tipo_materiale_sosp == "Molle":
                                    dur_opts = ["Molle morbide", "Molle medie", "Molle dure"]
                                    def_dur = (
                                        edit_data.get(f"Durezza_Molla_{tipo_sosp}", "Molle morbide")
                                        if edit_data
                                        else "Molle morbide"
                                    )
                                    idx_dur = dur_opts.index(def_dur) if def_dur in dur_opts else 0
                                    durezza_molla = st.selectbox(
                                        "Durezza",
                                        dur_opts,
                                        index=idx_dur,
                                        key=f"thunder_sosp_{key_base}_durezza_{model_safe_key}",
                                    )
                                    scelte_utente[f"Durezza_Molla_{tipo_sosp}"] = durezza_molla

                elif selected_prod_name.lower() == "scaleauto":
                    scaleauto_campi = [
                        "Motore",
                        "Supporto Motore",
                        "Corona",
                        "Giri Motore",
                        "Pignoni",
                        "Telaio",
                        "Assale Anteriore",
                        "Assale Posteriore",
                        "Cerchi Anteriori",
                        "Cerchi Posteriori",
                        "Pickup",
                        "Viti Carrozzeria",
                    ]

                    cols = st.columns(3)
                    for idx, campo in enumerate(scaleauto_campi):
                        with cols[idx % 3]:
                            if campo == "Giri Motore":
                                scelte_utente["Giri_Motore"] = st.text_input(
                                    "Giri Motore",
                                    value=(
                                        str(edit_data.get("Giri_Motore", "")) if edit_data else ""
                                    ),
                                    key=f"giri_motore_scaleauto_{model_safe_key}",
                                )
                            else:
                                sub_pezzi = helper_filtra_pezzi(campo)
                                scelte_utente[campo] = render_select_componente(
                                    campo, sub_pezzi, "scaleauto"
                                )

        # --- SEZIONE NOTE PER TUTTI I PRODUTTORI ---
        st.divider()
        st.markdown("### 📝 Note Personali di Setup/Collaudo (Opzionale)")
        note_text = st.text_area(
            "Aggiungi note personali su questo setup (es. feeling, adesione, problemi riscontrati)",
            value=str(edit_data.get("Note", "")) if edit_data else "",
            height=100,
            key=f"note_setup_{model_safe_key}",
        )
        scelte_utente["Note"] = note_text

        # --- PULSANTI SALVA MODIFICHE E SCARICA PDF ---
        st.divider()
        col_salva, col_pdf, col_cancella = st.columns(3)

        with col_salva:
            if st.button("💾 Salva Configurazione", key=f"save_config_{model_safe_key}"):
                # Verifica autenticazione (semplice check)
                if "user_id" not in st.session_state or st.session_state.user_id is None:
                    st.warning("⚠️ Devi effettuare il login per salvare le configurazioni!")
                    st.info("👤 Vai alla sezione **'🚗 Il Mio Garage'** per fare login o registrati.")
                else:
                    try:
                        config_data = {
                            "user_id": st.session_state.user_id,
                            "model_name": selected_model_name,
                            "producer_name": selected_prod_name,
                            "category_name": selected_cat_name,
                            "configuration_data": scelte_utente,
                            "foto_personalizzata_url": foto_personalizzata_finale,
                            "created_at": "now()",
                        }
                        
                        if st.session_state.modifying_config_id:
                            supabase.table("UserConfigurations").update(config_data).eq(
                                "id", st.session_state.modifying_config_id
                            ).execute()
                            st.success(f"✅ Configurazione '{selected_model_name}' aggiornata con successo!")
                            st.session_state.modifying_config_id = None
                            st.session_state.modifying_data = None
                            st.session_state.modifying_config_name = ""
                        else:
                            supabase.table("UserConfigurations").insert(config_data).execute()
                            st.success(f"✅ Configurazione '{selected_model_name}' salvata con successo!")
                        
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Errore durante il salvataggio: {e}")

        with col_pdf:
            if st.button("📄 Scarica PDF", key=f"download_pdf_{model_safe_key}"):
                try:
                    pdf_data = generate_pdf(
                        config_name=selected_model_name,
                        modello_nome=selected_model_name,
                        dettagli=scelte_utente,
                        foto_url=foto_personalizzata_finale,
                    )
                    st.download_button(
                        label="⬇️ Scarica Scheda PDF",
                        data=pdf_data,
                        file_name=f"SlotGarage_{selected_model_name}_{int(time.time())}.pdf",
                        mime="application/pdf",
                        key=f"pdf_download_{model_safe_key}",
                    )
                except Exception as e:
                    st.error(f"❌ Errore nella generazione del PDF: {e}")

        with col_cancella:
            if st.button("🗑️ Cancella Setup", key=f"cancel_config_{model_safe_key}"):
                if st.session_state.modifying_config_id:
                    try:
                        supabase.table("UserConfigurations").delete().eq(
                            "id", st.session_state.modifying_config_id
                        ).execute()
                        st.success("✅ Configurazione eliminata!")
                        st.session_state.modifying_config_id = None
                        st.session_state.modifying_data = None
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Errore durante l'eliminazione: {e}")
                else:
                    st.info("ℹ️ Nessuna configurazione in modifica da eliminare.")

# --- SEZIONE IL MIO GARAGE (GESTIONE CONFIGURAZIONI) ---
elif st.session_state.active_tab == "🚗 Il Mio Garage":
    st.header("🚗 Il Mio Garage - Le Tue Configurazioni")
    
    # Sistema di autenticazione semplice
    if "user_id" not in st.session_state:
        st.session_state.user_id = None
    
    if st.session_state.user_id is None:
        st.subheader("👤 Autenticazione")
        
        # --- LOGIN FORM ---
        col_login1, col_login2 = st.columns(2)
        with col_login1:
            username_login = st.text_input("Nome utente", key="username_login")
        with col_login2:
            password_login = st.text_input("Password", type="password", key="password_login")
        
        if st.button("🔓 Accedi", key="login_btn", use_container_width=True):
            if username_login and password_login:
                try:
                    st.info(f"🔍 Cerco utente: **{username_login}**...")
                    # Verifica credenziali su Supabase
                    response = supabase.table("Users").select("*").eq("username", username_login).execute()
                    st.write(f"📊 Risultati: {len(response.data) if response.data else 0} utente(i)")
                    
                    if response.data and len(response.data) > 0:
                        user = response.data[0]
                        st.write(f"👤 ID: {user.get('id')}, Username: {user.get('username')}")
                        # Verifica password
                        if user.get("password") == password_login:
                            st.session_state.user_id = user.get("id")
                            st.session_state.username = user.get("username")
                            st.success(f"✅ Benvenuto, {user.get('username')}!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"❌ Password incorretta!")
                    else:
                        st.error(f"❌ Utente '{username_login}' non trovato! Registrati prima.")
                except Exception as e:
                    st.error(f"❌ Errore: {str(e)}")
                    import traceback
                    st.write(traceback.format_exc())
            else:
                st.warning("⚠️ Inserisci username e password!")
        
        # --- REGISTRAZIONE IN EXPANDER ---
        with st.expander("📝 Crea un Nuovo Account"):
            st.markdown("### Registrati Ora")
            username_reg = st.text_input("Nome utente", key="username_reg")
            email_reg = st.text_input("Email", key="email_reg")
            password_reg = st.text_input("Password", type="password", key="password_reg")
            password_reg_confirm = st.text_input("Conferma Password", type="password", key="password_reg_confirm")
            
            if st.button("✍️ Registrati", key="register_btn", use_container_width=True):
                if not (username_reg and email_reg and password_reg and password_reg_confirm):
                    st.warning("⚠️ Completa tutti i campi!")
                elif password_reg != password_reg_confirm:
                    st.error("❌ Le password non coincidono!")
                else:
                    try:
                        st.info(f"🔍 Verifico se **{username_reg}** esiste già...")
                        # Verifica se username esiste già
                        check_user = supabase.table("Users").select("*").eq("username", username_reg).execute()
                        st.write(f"📊 Risultati: {len(check_user.data) if check_user.data else 0} utente(i)")
                        
                        if check_user.data and len(check_user.data) > 0:
                            st.error("❌ Username già utilizzato! Scegline un altro.")
                        else:
                            st.info("📝 Inserisco nuovo account...")
                            # Crea nuovo utente
                            new_user = {
                                "username": username_reg,
                                "email": email_reg,
                                "password": password_reg,
                            }
                            result = supabase.table("Users").insert(new_user).execute()
                            st.write(f"✅ Account creato!")
                            st.success("✅ Registrazione completata! Ora puoi fare il login.")
                            time.sleep(1)
                            st.rerun()
                    except Exception as e:
                        st.error(f"❌ Errore durante la registrazione: {str(e)}")
                        import traceback
                        st.write(traceback.format_exc())
    
    else:
        st.success(f"✅ Loggato come: **{st.session_state.get('username', 'Utente')}**")
        
        if st.button("🚪 Logout", key="logout_btn"):
            st.session_state.user_id = None
            st.session_state.username = None
            st.rerun()
        
        st.divider()
        
        # Carica configurazioni utente
        try:
            configs_response = supabase.table("UserConfigurations").select("*").eq(
                "user_id", st.session_state.user_id
            ).execute()
            
            configs = configs_response.data if configs_response and configs_response.data else []
            
            if not configs:
                st.info("ℹ️ Non hai ancora salvato nessuna configurazione. Vai a '📋 Visualizza Modelli' per crearne una!")
            else:
                st.subheader(f"📚 Le Tue Configurazioni ({len(configs)})")
                
                for config in configs:
                    with st.expander(f"🏎️ {config.get('model_name')} - {config.get('producer_name')}"):
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            if st.button("✏️ Modifica", key=f"edit_config_{config.get('id')}"):
                                st.session_state.modifying_config_id = config.get("id")
                                st.session_state.modifying_data = config.get("configuration_data")
                                st.session_state.modifying_config_name = config.get("model_name")
                                st.session_state.modifying_model_name = config.get("model_name")
                                st.session_state.active_tab = "📋 Visualizza Modelli"
                                st.rerun()
                        
                        with col2:
                            if st.button("📄 Scarica PDF", key=f"view_pdf_{config.get('id')}"):
                                try:
                                    pdf_data = generate_pdf(
                                        config_name=config.get("model_name"),
                                        modello_nome=config.get("model_name"),
                                        dettagli=config.get("configuration_data"),
                                        foto_url=config.get("foto_personalizzata_url"),
                                    )
                                    st.download_button(
                                        label="⬇️ Scarica",
                                        data=pdf_data,
                                        file_name=f"SlotGarage_{config.get('model_name')}.pdf",
                                        mime="application/pdf",
                                        key=f"pdf_download_garage_{config.get('id')}",
                                    )
                                except Exception as e:
                                    st.error(f"❌ Errore PDF: {e}")
                        
                        with col3:
                            if st.button("🗑️ Elimina", key=f"delete_config_{config.get('id')}"):
                                try:
                                    supabase.table("UserConfigurations").delete().eq(
                                        "id", config.get("id")
                                    ).execute()
                                    st.success("✅ Configurazione eliminata!")
                                    st.cache_data.clear()
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Errore: {e}")
                        
                        st.markdown(f"**Produttore:** {config.get('producer_name')}")
                        st.markdown(f"**Categoria:** {config.get('category_name')}")
                        st.json(config.get("configuration_data"), expanded=False)
        
        except Exception as e:
            st.error(f"❌ Errore nel caricamento configurazioni: {e}")

# --- SEZIONE IL MIO PULSANTE (GESTIONE PULSANTI) ---
elif st.session_state.active_tab == "🎛️ Il Mio Pulsante":
    st.header("🎛️ Il Mio Pulsante - Configurazione Hardware")
    
    if "user_id" not in st.session_state or st.session_state.user_id is None:
        st.warning("⚠️ Devi effettuare il login in '🚗 Il Mio Garage' per accedere a questa sezione!")
    else:
        st.info("🔨 Sezione dedicata alla configurazione dei pulsanti di comando per il tuo controller.")
        
        st.subheader("⚙️ Impostazioni Pulsante")
        col1, col2 = st.columns(2)
        
        with col1:
            pulsante_nome = st.text_input(
                "Nome Pulsante",
                value=st.session_state.get("modifying_pulsante_data", {}).get("nome", ""),
                key="pulsante_nome",
            )
            pulsante_pin = st.number_input(
                "Pin GPIO",
                min_value=1,
                max_value=28,
                value=int(st.session_state.get("modifying_pulsante_data", {}).get("pin", 0)) or 1,
                key="pulsante_pin",
            )
        
        with col2:
            pulsante_funzione = st.selectbox(
                "Funzione",
                ["Accelera", "Frena", "Reset", "Personalizzata"],
                index=0,
                key="pulsante_funzione",
            )
            pulsante_sensibilita = st.slider(
                "Sensibilità (%)",
                min_value=0,
                max_value=100,
                value=int(st.session_state.get("modifying_pulsante_data", {}).get("sensibilita", 50)) or 50,
                key="pulsante_sensibilita",
            )
        
        if st.button("💾 Salva Pulsante", key="save_pulsante"):
            pulsante_data = {
                "user_id": st.session_state.user_id,
                "nome": pulsante_nome,
                "pin": pulsante_pin,
                "funzione": pulsante_funzione,
                "sensibilita": pulsante_sensibilita,
            }
            
            try:
                if st.session_state.modifying_pulsante_id:
                    supabase.table("UserPulsanti").update(pulsante_data).eq(
                        "id", st.session_state.modifying_pulsante_id
                    ).execute()
                    st.success("✅ Pulsante aggiornato!")
                else:
                    supabase.table("UserPulsanti").insert(pulsante_data).execute()
                    st.success("✅ Pulsante salvato!")
                
                st.session_state.modifying_pulsante_id = None
                st.session_state.modifying_pulsante_data = None
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"❌ Errore: {e}")

# --- SEZIONE CARICA MODELLO (AGGIUNTA NUOVI MODELLI) ---
elif st.session_state.active_tab == "➕ Carica Modello":
    st.header("➕ Carica Modello - Aggiungi Nuovo Modello")
    
    if "user_id" not in st.session_state or st.session_state.user_id is None:
        st.warning("⚠️ Devi effettuare il login in '🚗 Il Mio Garage' per caricare nuovi modelli!")
    else:
        st.info("📤 Aggiungi un nuovo modello di auto al database della comunità.")
        
        st.subheader("📋 Dettagli Modello")
        col1, col2 = st.columns(2)
        
        with col1:
            nome_modello = st.text_input("Nome Modello", key="upload_model_name")
            produttore_id = st.selectbox(
                "Produttore",
                [p.get("id") for p in produttori if p],
                format_func=lambda x: next((p.get("name") for p in produttori if p and p.get("id") == x), ""),
                key="upload_producer_id",
            )
        
        with col2:
            categoria_id = st.selectbox(
                "Categoria",
                [c.get("id") for c in categorie if c],
                format_func=lambda x: next((c.get("name") for c in categorie if c and c.get("id") == x), ""),
                key="upload_category_id",
            )
            scala = st.selectbox("Scala", ["1:32", "1:24", "1:43", "Altra"], key="upload_scala")
        
        st.subheader("📸 Foto Modello")
        foto_modello = st.file_uploader(
            "Carica foto modello",
            type=["jpg", "jpeg", "png"],
            key="upload_model_photo",
        )
        
        st.subheader("📝 Descrizione")
        descrizione = st.text_area("Descrizione modello", height=100, key="upload_model_desc")
        
        if st.button("🚀 Carica Modello", key="upload_model_btn"):
            if not (nome_modello and produttore_id and categoria_id):
                st.error("❌ Completa i campi obbligatori!")
            else:
                try:
                    foto_url = None
                    if foto_modello:
                        foto_url = upload_image_to_supabase(foto_modello)
                    
                    nuovo_modello = {
                        "name": nome_modello,
                        "producer_id": produttore_id,
                        "category_id": categoria_id,
                        "scala": scala,
                        "foto_url": foto_url,
                        "descrizione": descrizione,
                        "submitted_by": st.session_state.user_id,
                        "created_at": "now()",
                    }
                    
                    supabase.table("MODELLI").insert(nuovo_modello).execute()
                    st.success(f"✅ Modello '{nome_modello}' caricato con successo! Grazie per il contributo! 🎉")
                    st.cache_data.clear()
                    time.sleep(2)
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Errore durante il caricamento: {e}")
