import ast
import os
import time
import tempfile
from fpdf import FPDF
import requests
import streamlit as st
from supabase import create_client, ClientOptions

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
    options = ClientOptions(persist_session=True)
    return create_client(SUPABASE_URL, SUPABASE_KEY, options=options)
  except Exception as e:
    st.error(f"Errore di connessione a Supabase: {e}")
    return None


supabase = init_connection()

LOGO_PATH = "logo.png"

st.set_page_config(page_title="SlotGarage", page_icon=LOGO_PATH, layout="wide")

# --- GESTIONE STATO UTENTE & PERSISTENZA SESSIONE ---
if "user" not in st.session_state:
  if supabase and supabase.auth.get_session():
    st.session_state.user = supabase.auth.get_session().user
  else:
    st.session_state.user = None

if "pending_garage_data" not in st.session_state:
  st.session_state.pending_garage_data = None

# Funzione per completare automaticamente il salvataggio se l'utente si è loggato ora
def process_pending_garage():
  if st.session_state.pending_garage_data and st.session_state.user:
    p = st.session_state.pending_garage_data
    try:
      record_garage = {
          "nome_configurazione": p["nome_configurazione"],
          "modello_nome": p["modello_nome"],
          "dettagli_setup": str(p["dettagli_setup"]),
          "user_id": st.session_state.user.id
      }
      if p["is_update"]:
        supabase.table("IlMioGarage").update(record_garage).eq("id", p["config_id"]).eq("user_id", st.session_state.user.id).execute()
        st.success(f"Configurazione '{p['nome_configurazione']}' aggiornata con successo dopo il login!")
        st.session_state.modifying_config_id = None
        st.session_state.modifying_data = None
        st.session_state.modifying_config_name = ""
        if "modifying_model_name" in st.session_state:
          del st.session_state.modifying_model_name
      else:
        supabase.table("IlMioGarage").insert(record_garage).execute()
        st.success(f"Configurazione '{p['nome_configurazione']}' salvata con successo nel tuo Garage dopo il login!")
    except Exception as e:
      st.error(f"Errore durante il salvataggio post-login: {e}")
    finally:
      st.session_state.pending_garage_data = None
      st.session_state.active_tab = "🚗 Il Mio Garage"
      st.rerun()

process_pending_garage()

# Funzione di supporto per mostrare il form di autenticazione e registrazione stabile
def richiedi_autenticazione():
  st.warning("⚠️ Per procedere devi effettuare l'accesso o registrarti.")
  
  tab_login, tab_reg = st.tabs(["Accedi", "Registrati"])
  
  with tab_login:
    with st.form("modal_login_form_definitivo"):
      email_in = st.text_input("Email", key="modal_login_email_def")
      pass_in = st.text_input("Password", type="password", key="modal_login_password_def")
      if st.form_submit_button("Conferma Accesso"):
        try:
          res = supabase.auth.sign_in_with_password({"email": email_in, "password": pass_in})
          st.session_state.user = res.user
          st.success("Accesso effettuato con successo!")
          st.rerun()
        except Exception as e:
          st.error(f"Errore di autenticazione: {e}")
        
  with tab_reg:
    with st.form("modal_reg_form_definitivo"):
      email_reg = st.text_input("Email", key="modal_reg_email_def")
      pass_reg = st.text_input("Password", type="password", key="modal_reg_password_def")
      if st.form_submit_button("Crea Account"):
        try:
          supabase.auth.sign_up({"email": email_reg, "password": pass_reg})
          st.success("Registrazione completata! Effettua il login nella scheda accanto.")
        except Exception as e:
          st.error(f"Errore durante la registrazione: {e}")

# --- BARRA LATERALE: INFO UTENTE E STATO ---
with st.sidebar:
  if st.session_state.user:
    st.write(f"Pilota loggato: **{st.session_state.user.email}**")
    if st.button("🚪 Logout"):
      supabase.auth.sign_out()
      st.session_state.user = None
      st.rerun()
  else:
    st.info("Stai navigando come Ospite.")
    with st.expander("🔑 Accedi"):
      with st.form("sb_login_form_definitivo"):
        email_sb = st.text_input("Email", key="sb_email_def")
        pass_sb = st.text_input("Password", type="password", key="sb_pass_def")
        if st.form_submit_button("Login rapido", key="sb_login_btn_def"):
          try:
            res = supabase.auth.sign_in_with_password({"email": email_sb, "password": pass_sb})
            st.session_state.user = res.user
            st.rerun()
          except Exception as e:
            st.error(f"Errore: {e}")
  st.divider()

# --- INTESTAZIONE CON LOGO E SCRITTA INGRANDITA E ABBASSATA ---
col_logo, col_titolo = st.columns([2, 10])
with col_logo:
  try:
    st.image(LOGO_PATH, width=220)
  except Exception:
    st.write("🏎️")
with col_titolo:
  st.markdown(
      "<h1 style='margin-top: 25px; font-size: clamp(2.5rem, 5vw, 4.2rem); margin-bottom:"
      " 0px; white-space: nowrap;'>SlotGarage</h1><p style='color: #FFD700; font-size: 1.3rem;"
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
st.header("🔍 Filtra Modello")

produttori_filtrati_list = [
    p for p in produttori 
    if p and p.get("name") and p.get("id") and str(p.get("name")).strip().upper() not in ["BRM", "REVOSLOT"]
]

prod_options = {
    p.get("name"): p.get("id")
    for p in produttori_filtrati_list
}
prod_options["Altri Produttori"] = "altri_produttori_custom_id"

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
  elif mod_name_target == "Altro":
    pre_selected_mod = "Altro"
    pre_selected_cat = "Altro"
    pre_selected_prod = "Altri Produttori"

col_f1, col_f2, col_f3 = st.columns(3)

prod_names_list = ["Tutti"] + list(prod_options.keys())
if pre_selected_prod in prod_names_list:
  default_prod_idx = prod_names_list.index(pre_selected_prod)

with col_f1:
  selected_prod_name = st.selectbox(
      "Seleziona Produttore", prod_names_list, index=default_prod_idx
  )

if selected_prod_name != "Tutti" and selected_prod_name != "Altri Produttori":
  prod_id = prod_options[selected_prod_name]
  cat_options = {
      c.get("name"): c.get("id")
      for c in categorie
      if c and c.get("brand_it") == prod_id
  }
elif selected_prod_name == "Altri Produttori":
  cat_options = {"Altro": "altro_cat_id"}
else:
  cat_options = {
      c.get("name"): c.get("id")
      for c in categorie
      if c and c.get("name") and c.get("id")
  }

cat_names_list = ["Tutte"] + list(cat_options.keys())
if pre_selected_cat in cat_names_list:
  default_cat_idx = cat_names_list.index(pre_selected_cat)

with col_f2:
  selected_cat_name = st.selectbox(
      "Seleziona Categoria", cat_names_list, index=default_cat_idx
  )

if selected_cat_name != "Tutte":
  cat_id = cat_options.get(selected_cat_name)
  if selected_prod_name == "Altri Produttori":
    mod_list = ["Altro"]
  else:
    mod_list = [
        m.get("name")
        for m in modelli
        if m and m.get("category_id") == cat_id and m.get("name")
    ]
else:
  if selected_prod_name == "Altri Produttori":
    mod_list = ["Altro"]
  else:
    mod_list = [m.get("name") for m in modelli if m and m.get("name")]

mod_names_list = ["Tutti"] + mod_list
if pre_selected_mod in mod_names_list:
  default_mod_idx = mod_names_list.index(pre_selected_mod)

with col_f3:
  selected_model_name = st.selectbox("Seleziona Modello", mod_names_list, index=default_mod_idx)

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

  pesi_motore_keywords = [
      "peso_carrozzeria",
      "peso_totale",
      "misura_assale_post.",
      "giri_motore",
      "motore",
      "supporto_motore",
      "corona",
      "pignoni",
  ]

  dettagli_filtrati = {}
  for k, v in dettagli.items():
    if k.lower() == "note" or k.lower() == "foto_personalizzata_url":
      continue
    if k in ["Distanziali_Ant.", "Distanziali_Post."]:
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

  left_items = {}
  right_items = {}
  for k, v in dettagli_filtrati.items():
    k_norm = k.lower().replace(" ", "_")
    if any(pk in k_norm for pk in pesi_motore_keywords):
      left_items[k] = v
    else:
      right_items[k] = v

  def draw_tech_section(x, y, w, title, items_dict):
    pdf.set_fill_color(*bg_dark)
    pdf.set_text_color(*text_light)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_xy(x, y)
    pdf.cell(w, 6, f"   {title}", ln=True, fill=True)

    item_y = y + 7.5
    for k, v in items_dict.items():
      if not v or str(v).lower() == "no" or str(v).lower() == "nessuna":
        continue
      pdf.set_text_color(*text_dark)
      pdf.set_font("Helvetica", "", 8.5)
      
      # MODIFICA APPLICATA: Pulizia etichette e abbreviazione automatica di "Sospensioni" in "Sosp."
      k_clean = str(k).replace("_", " ")
      k_clean = k_clean.replace("Sospensioni", "Sosp.")
      v_clean = str(v)

      # MODIFICA APPLICATA: Larghezza etichetta portata a 42mm e valore spostato a x + 45 per distanziare i testi
      pdf.set_xy(x + 3, item_y)
      pdf.cell(42, 4.8, f"{k_clean}:", 0, 0)

      pdf.set_font("Helvetica", "B", 8.5)
      pdf.set_xy(x + 45, item_y)

      start_val_y = pdf.get_y()
      pdf.multi_cell(w - 48, 4.2, f"{v_clean}")
      end_val_y = pdf.get_y()

      row_height = max(4.8, (end_val_y - start_val_y))
      item_y += row_height + 0.8

    return item_y - y

  box_start_y = 24
  h_col1 = draw_tech_section(
      col1_x,
      box_start_y,
      col_w,
      "MOTORE & PESI",
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
    pdf.cell(189, 5, "   NOTE", ln=True, fill=True)

    pdf.set_text_color(*text_dark)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_xy(col1_x + 3, next_y + 5.5)
    pdf.multi_cell(183, 4, str(note_val))

  pdf_data = pdf.output(dest="S")
  if isinstance(pdf_data, str):
    return pdf_data.encode("latin1")
  return bytes(pdf_data)


# --- GESTIONE SEZIONI (TAB) ---

if st.session_state.active_tab == "📋 Visualizza Modelli":
  if selected_model_name != "Tutti":
    if selected_prod_name == "Altri Produttori" and selected_model_name != "Altro":
      st.info("Per 'Altri Produttori', seleziona 'Altro' come modello per procedere con la configurazione personalizzata.")
    else:
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
        )

      st.subheader(f"Configurazione: {selected_model_name}")

      default_foto_db = (
