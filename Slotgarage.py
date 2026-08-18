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
      col_foto_up1, col_foto_up2 = st.columns(2)
      with col_foto_up1:
        file_foto_pers = st.file_uploader(
            "Carica immagine dal dispositivo",
            type=["jpg", "jpeg", "png"],
            key="file_foto_pers_setup",
        )
      with col_foto_up2:
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
              key=f"{key_prefix}_{campo}_{model_safe_key}",
          )

        if selected_prod_name == "Altri Produttori":
          col_p1, col_p2, col_p3 = st.columns(3)
          with col_p1:
            scelte_utente["Peso_Carrozzeria"] = st.text_input(
                "Peso Carrozzeria",
                value=str(edit_data.get("Peso_Carrozzeria", "")) if edit_data else "",
                key=f"peso_carrozzeria_altri_{model_safe_key}",
            )
          with col_p2:
            scelte_utente["Peso_Totale"] = st.text_input(
                "Peso Totale",
                value=str(edit_data.get("Peso_Totale", "")) if edit_data else "",
                key=f"peso_totale_altri_{model_safe_key}",
            )
          with col_p3:
            scelte_utente["Misura_Assale_Posteriore"] = st.text_input(
                "Misura Assale Posteriore",
                value=str(edit_data.get("Misura_Assale_Posteriore", "")) if edit_data else "",
                key=f"misura_assale_posteriore_{model_safe_key}"
            )

          altri_campi = [
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
          for idx, campo in enumerate(altri_campi):
            with cols[idx % 3]:
              val_salvato_campo = str(edit_data.get(campo, "")) if edit_data else ""
              scelte_utente[campo] = st.text_input(
                  campo,
                  value=val_salvato_campo,
                  key=f"altri_txt_{campo}_{model_safe_key}"
              )

          st.write("### 🔩 Sospensioni")
          sosp_altri_val = st.text_input(
              "Sospensioni",
              value=str(edit_data.get("Sospensioni", "")) if edit_data else "",
              key=f"altri_sospensioni_{model_safe_key}"
          )
          scelte_utente["Sospensioni"] = sosp_altri_val

          st.write("### 📏 Distanziali")
          col_d1, col_d2, col_d3 = st.columns(3)
          with col_d1:
            scelte_utente["Distanziali_Anteriori"] = st.text_input(
                "Distanziali anteriori",
                value=str(edit_data.get("Distanziali_Anteriori", "")) if edit_data else "",
                key=f"altri_dist_ant_{model_safe_key}"
            )
          with col_d2:
            scelte_utente["Distanziali_Posteriori"] = st.text_input(
                "Distanziali posteriori",
                value=str(edit_data.get("Distanziali_Posteriori", "")) if edit_data else "",
                key=f"altri_dist_post_{model_safe_key}"
            )
          with col_d3:
            scelte_utente["Distanziali_Pickup"] = st.text_input(
                "Distanziale Pickup",
                value=str(edit_data.get("Distanziali_Pickup", "")) if edit_data else "",
                key=f"altri_dist_pick_{model_safe_key}"
            )

          st.write("### 🔩 Supporto Assale")
          scelte_utente["Tipo_Supporto"] = st.text_input(
              "Tipo Supporto / Dettaglio Supporto",
              value=str(edit_data.get("Tipo_Supporto", "")) if edit_data else "",
              key=f"altri_tipo_supporto_{model_safe_key}"
          )

        elif selected_prod_name.lower() == "slot.it":
          col1_slot, col2_slot, col3_slot = st.columns(3)
          with col1_slot:
            cat_slot_opts = ["Nessuna", "P1", "P2", "Prototipi", "Sport"]
            def_cat_slot = edit_data.get("Categoria_SlotIt", "Nessuna") if edit_data else "Nessuna"
            idx_cat_slot = cat_slot_opts.index(def_cat_slot) if def_cat_slot in cat_slot_opts else 0
            scelte_utente["Categoria_SlotIt"] = st.selectbox(
                "Categoria",
                cat_slot_opts,
                index=idx_cat_slot,
                key=f"slotit_categoria_{model_safe_key}",
            )
          with col2_slot:
            scelte_utente["Peso_Carrozzeria"] = st.text_input(
                "Peso Carrozzeria",
                value=str(edit_data.get("Peso_Carrozzeria", "")) if edit_data else "",
                key=f"peso_carrozzeria_{model_safe_key}",
            )
          with col3_slot:
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
                    value=str(edit_data.get("Giri_Motore", "")) if edit_data else "",
                    key=f"giri_motore_slotit_{model_safe_key}",
                )
              elif campo == "Stopper":
                col_stop_1, col_stop_2 = st.columns(2)
                with col_stop_1:
                  stopper_opts = ["No", "Sì"]
                  def_stop = edit_data.get("Stopper", "No") if edit_data else "No"
                  idx_stop = stopper_opts.index(def_stop) if def_stop in stopper_opts else 0
                  scelte_utente["Stopper"] = st.selectbox(
                      "Stopper", stopper_opts, index=idx_stop, key=f"slotit_stopper_{model_safe_key}"
                  )
                with col_stop_2:
                  scelte_utente["Misura_Assale_Posteriore"] = st.text_input(
                      "Misura Assale Posteriore",
                      value=str(edit_data.get("Misura_Assale_Posteriore", "")) if edit_data else "",
                      key=f"misura_assale_posteriore_{model_safe_key}"
                  )
              else:
                sub_pezzi = helper_filtra_pezzi(campo)
                scelte_utente[campo] = render_select_componente(campo, sub_pezzi, "slotit")

          st.write("### 🔩 Sospensioni")
          col_viti, col_tipo_sosp = st.columns(2)
          with col_viti:
            sub_viti_sosp = [
                p for p in pezzi if p and p.get("Prodotto") and p.get("Prodotto").strip().lower() == "viti metriche sospensioni"
            ]
            scelte_utente["Viti_Metriche_Sosp"] = render_select_componente("Viti_Metriche_Sospensioni", sub_viti_sosp, "slotit_viti")
          with col_tipo_sosp:
            tipo_sosp_opts = ["Molle", "Magneti"]
            def_t_sosp = edit_data.get("Tipo_Sospensione", "Molle") if edit_data else "Molle"
            idx_t_sosp = tipo_sosp_opts.index(def_t_sosp) if def_t_sosp in tipo_sosp_opts else 0
            tipo_sosp_slotit = st.selectbox(
                "Tipo Sospensione",
                tipo_sosp_opts,
                index=idx_t_sosp,
                key=f"slotit_tipo_sospensione_{model_safe_key}",
            )
            scelte_utente["Tipo_Sospensione"] = tipo_sosp_slotit

          if tipo_sosp_slotit == "Magneti":
            sub_sosp = [p for p in pezzi if p and p.get("Prodotto") and p.get("Prodotto").strip().lower() == "sospensioni magnetiche"]
          else:
            sub_sosp = [p for p in pezzi if p and p.get("Prodotto") and p.get("Prodotto").strip().lower() == "sospensioni"]
          
          scelte_utente["Sospensioni"] = render_select_componente("Sospensioni", sub_sosp, "slotit_scelta_sosp")

        else:
          col_p1, col_p2, col_p3 = st.columns(3)
          with col_p1:
            scelte_utente["Peso_Carrozzeria"] = st.text_input(
                "Peso Carrozzeria",
                value=str(edit_data.get("Peso_Carrozzeria", "")) if edit_data else "",
                key=f"peso_carrozzeria_{selected_prod_name}_{model_safe_key}",
            )
          with col_p2:
            scelte_utente["Peso_Totale"] = st.text_input(
                "Peso Totale",
                value=str(edit_data.get("Peso_Totale", "")) if edit_data else "",
                key=f"peso_totale_{selected_prod_name}_{model_safe_key}",
            )
          with col_p3:
            scelte_utente["Misura_Assale_Posteriore"] = st.text_input(
                "Misura Assale Posteriore",
                value=str(edit_data.get("Misura_Assale_Posteriore", "")) if edit_data else "",
                key=f"misura_assale_posteriore_{model_safe_key}"
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
                      value=str(edit_data.get("Giri_Motore", "")) if edit_data else "",
                      key=f"giri_motore_nsr_{model_safe_key}",
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
                      value=str(edit_data.get("Giri_Motore", "")) if edit_data else "",
                      key=f"giri_motore_thunder_{model_safe_key}",
                  )
                else:
                  sub_pezzi = helper_filtra_pezzi(campo)
                  scelte_utente[campo] = render_select_componente(campo, sub_pezzi, "thunder")

            st.write("### 🔩 Sospensioni")
            col_th_sos1, col_th_sos2, col_th_sos3 = st.columns(3)
            with col_th_sos1:
              sosp_th_opts = ["No", "Sì"]
              def_th_sos = edit_data.get("Sospensioni_ Posteriori", edit_data.get("Sospensioni", "No")) if edit_data else "No"
              idx_th_sos = sosp_th_opts.index(def_th_sos) if def_th_sos in sosp_th_opts else 0
              scelte_utente["Sospensioni_Posteriori"] = st.selectbox(
                  "Sospensioni Posteriori",
                  sosp_th_opts,
                  index=idx_th_sos,
                  key=f"th_sosp_post_{model_safe_key}"
              )
            with col_th_sos2:
              tipo_molla_th_opts = ["Molle morbide", "Molle medie", silv := "Molle dure"] if 'silv' in locals() else ["Molle dure"]
              scelte_utente["Tipo_Sospensione_Posteriori"] = st.selectbox(
                  "Tipo Sospensione Posteriori",
                  ["Molle morbide", "Molle medie", "Molle dure"],
                  key=f"th_tipo_sosp_post_{model_safe_key}"
              )
            with col_th_sos3:
              scelte_utente["Durezza_Molla_Posteriori"] = st.text_input(
                  "Durezza Molla Posteriori",
                  value=str(edit_data.get("Durezza_Molla_Posteriori", "")) if edit_data else "",
                  key=f"th_dur_molla_post_{model_safe_key}"
              )

            col_th_lat1, col_th_lat2 = st.columns(2)
            with col_th_lat1:
              scelte_utente["Sospensioni_Laterali"] = st.selectbox(
                  "Sospensioni Laterali",
                  ["No", "Sì"],
                  key=f"th_sosp_lat_{model_safe_key}"
              )
            with col_th_lat2:
              scelte_utente["Tipo_Sospensione_Laterali"] = st.selectbox(
                  "Tipo Sospensione Laterali",
                  ["Molle morbide", "Molle medie", "Molle dure"],
                  key=f"th_tipo_sosp_lat_{model_safe_key}"
              )

            col_th_ant1, col_th_ant2 = st.columns(2)
            with col_th_ant1:
              scelte_utente["Sospensioni_Anteriori"] = st.selectbox(
                  "Sospensioni Anteriori",
                  ["No", "Sì"],
                  key=f"th_sosp_ant_{model_safe_key}"
              )
            with col_th_ant2:
              scelte_utente["Tipo_Sospensione_Anteriori"] = st.selectbox(
                  "Tipo Sospensione Anteriori",
                  ["Molle morbide", "Molle medie", "Molle dure"],
                  key=f"th_tipo_sosp_ant_{model_safe_key}"
              )

        st.divider()
        st.write("### 📏 Distanziali e Supporto Assale")
        col_sup1, col_sup2 = st.columns(2)
        with col_sup1:
          tipo_sup_opts = ["Bronzine", "Cuscinetti a sfera"]
          def_t_sup = edit_data.get("Tipo_Supporto", "Bronzine") if edit_data else "Bronzine"
          idx_t_sup = tipo_sup_opts.index(def_t_sup) if def_t_sup in tipo_sup_opts else 0
          scelte_utente["Tipo_Supporto"] = st.selectbox(
              "Tipo Supporto",
              tipo_sup_opts,
              index=idx_t_sup,
              key=f"tipo_supporto_generico_{model_safe_key}"
          )
        with col_sup2:
          sub_dett_sup = [p for p in pezzi if p and p.get("Prodotto") and ("supporto" in p.get("Prodotto").lower() or "bronz" in p.get("Prodotto").lower() or "cuscinett" in p.get("Prodotto").lower())]
          scelte_utente["Dettaglio_Supporto"] = render_select_componente("Dettaglio_Supporto", sub_dett_sup, "dettaglio_sup")

        col_dist1, col_dist2, col_dist3 = st.columns(3)
        with col_dist1:
          sub_dist_ant = [p for p in pezzi if p and p.get("Prodotto") and "distanzial" in p.get("Prodotto").lower() and "anteri" in p.get("Prodotto").lower()]
          scelte_utente["Distanziali_Ant."] = render_select_componente("Distanziali_Ant.", sub_dist_ant, "dist_ant")
        with col_dist2:
          sub_dist_post = [p for p in pezzi if p and p.get("Prodotto") and "distanzial" in p.get("Prodotto").lower() and "posteri" in p.get("Prodotto").lower()]
          scelte_utente["Distanziali_Post."] = render_select_componente("Distanziali_Post.", sub_dist_post, "dist_post")
        with col_dist3:
          sub_pick = [p for p in pezzi if p and p.get("Prodotto") and "distanzial" in p.get("Prodotto").lower() and "pickup" in p.get("Prodotto").lower()]
          scelte_utente["Distanziali_Pickup"] = render_select_componente("Distanziali_Pickup", sub_pick, "dist_pick")

        st.divider()
        st.write("### 📝 Note e Personalizzazioni")
        note_utente = st.text_area(
            "Note",
            value=str(edit_data.get("Note", "")) if edit_data else "",
            key=f"note_setup_{model_safe_key}"
        )
        scelte_utente["Note"] = note_utente
        scelte_utente["foto_personalizzata_url"] = foto_personalizzata_finale

        st.divider()
        nome_config_input = st.text_input(
            "Nome Configurazione",
            value=st.session_state.get("modifying_config_name", f"Setup {selected_model_name}"),
            key=f"nome_config_input_{model_safe_key}"
        )

        col_act1, col_act2 = st.columns(2)
        with col_act1:
          if st.button("💾 Salva nel Mio Garage", type="primary", key=f"btn_salva_garage_{model_safe_key}"):
            if not nome_config_input.strip():
              st.error("Inserisci un nome valido per la configurazione.")
            else:
              if not st.session_state.user:
                st.session_state.pending_garage_data = {
                    "nome_configurazione": nome_config_input,
                    "modello_nome": selected_model_name,
                    "dettagli_setup": scelte_utente,
                    "is_update": bool(st.session_state.modifying_config_id),
                    "config_id": st.session_state.modifying_config_id
                }
                richiedi_autenticazione()
              else:
                try:
                  record_garage = {
                      "nome_configurazione": nome_config_input,
                      "modello_nome": selected_model_name,
                      "dettagli_setup": str(scelte_utente),
                      "user_id": st.session_state.user.id
                  }
                  if st.session_state.modifying_config_id:
                    supabase.table("IlMioGarage").update(record_garage).eq("id", st.session_state.modifying_config_id).eq("user_id", st.session_state.user.id).execute()
                    st.success(f"Configurazione '{nome_config_input}' aggiornata con successo!")
                    st.session_state.modifying_config_id = None
                    st.session_state.modifying_data = None
                    st.session_state.modifying_config_name = ""
                    if "modifying_model_name" in st.session_state:
                      del st.session_state.modifying_model_name
                  else:
                    supabase.table("IlMioGarage").insert(record_garage).execute()
                    st.success(f"Configurazione '{nome_config_input}' salvata con successo nel tuo Garage!")
                  st.session_state.active_tab = "🚗 Il Mio Garage"
                  st.rerun()
                except Exception as e:
                  st.error(f"Errore durante il salvataggio: {e}")

        with col_act2:
          if st.button("📥 Scarica PDF al Volo", key=f"btn_pdf_volo_{model_safe_key}"):
            try:
              pdf_bytes = generate_pdf(
                  nome_config_input,
                  selected_model_name,
                  scelte_utente,
                  foto_url=foto_personalizzata_finale or default_foto_db
              )
              st.download_button(
                  label="💾 Conferma Download PDF",
                  data=pdf_bytes,
                  file_name=f"{selected_model_name.replace(' ', '_')}_scheda_tecnica.pdf",
                  mime="application/pdf",
                  key=f"download_pdf_confirm_{model_safe_key}"
              )
            except Exception as e:
              st.error(f"Errore nella generazione del PDF: {e}")

  else:
    st.info("Seleziona un produttore e un modello specifico dai filtri in alto per visualizzare e configurare la scheda tecnica.")

elif st.session_state.active_tab == "🚗 Il Mio Garage":
  st.header("🚗 Il Mio Garage")
  if not st.session_state.user:
    st.warning("⚠️ Devi effettuare l'accesso per visualizzare e gestire i setup salvati nel tuo garage.")
    richiedi_autenticazione()
  else:
    try:
      response_garage = supabase.table("IlMioGarage").select("*").eq("user_id", st.session_state.user.id).execute()
      miei_setup = response_garage.data if response_garage and response_garage.data else []

      if not miei_setup:
        st.info("Il tuo garage è ancora vuoto. Crea e salva una configurazione dalla sezione 'Visualizza Modelli'.")
      else:
        for idx, setup in enumerate(miei_setup):
          with st.expander(f"🏎️ {setup.get('nome_configurazione')} — Modello: {setup.get('modello_nome')}"):
            st.write(f"**Modello:** {setup.get('modello_nome')}")
            
            dettagli_raw = setup.get("dettagli_setup")
            diz_dettagli = {}
            if dettagli_raw:
              try:
                if isinstance(dettagli_raw, str):
                  diz_dettagli = ast.literal_eval(dettagli_raw)
                elif isinstance(dettagli_raw, dict):
                  diz_dettagli = dettagli_raw
              except Exception:
                diz_dettagli = {"Nota": "Errore lettura dettagli"}

            foto_setup_url = diz_dettagli.get("foto_personalizzata_url")
            if foto_setup_url:
              try:
                st.image(foto_setup_url, width=200)
              except Exception:
                pass

            st.json(diz_dettagli)

            col_g1, col_g2, col_g3 = st.columns(3)
            with col_g1:
              if st.button("✏️ Modifica Setup", key=f"mod_garage_{setup.get('id')}_{idx}"):
                st.session_state.modifying_config_id = setup.get("id")
                st.session_state.modifying_data = diz_dettagli
                st.session_state.modifying_config_name = setup.get("nome_configurazione")
                st.session_state.modifying_model_name = setup.get("modello_nome")
                st.session_state.active_tab = "📋 Visualizza Modelli"
                st.rerun()

            with col_g2:
              if st.button("📄 Scarica PDF", key=f"pdf_garage_{setup.get('id')}_{idx}"):
                try:
                  pdf_bytes = generate_pdf(
                      setup.get("nome_configurazione"),
                      setup.get("modello_nome"),
                      diz_dettagli,
                      foto_url=foto_setup_url
                  )
                  st.download_button(
                      label="💾 Scarica PDF Scheda",
                      data=pdf_bytes,
                      file_name=f"{setup.get('nome_configurazione').replace(' ', '_')}.pdf",
                      mime="application/pdf",
                      key=f"dl_pdf_garage_{setup.get('id')}_{idx}"
                  )
                except Exception as e:
                  st.error(f"Errore PDF: {e}")

            with col_g3:
              if st.button("🗑️ Elimina", key=f"del_garage_{setup.get('id')}_{idx}"):
                try:
                  supabase.table("IlMioGarage").delete().eq("id", setup.get("id")).eq("user_id", st.session_state.user.id).execute()
                  st.success("Configurazione eliminata con successo!")
                  st.rerun()
                except Exception as e:
                  st.error(f"Errore durante l'eliminazione: {e}")

    except Exception as e:
      st.error(f"Errore nel caricamento del garage: {e}")

elif st.session_state.active_tab == "🎛️ Il Mio Pulsante":
  st.header("🎛️ Il Mio Pulsante (Controller)")
  if not st.session_state.user:
    st.warning("⚠️ Effettua l'accesso per gestire le configurazioni del tuo pulsante.")
    richiedi_autenticazione()
  else:
    try:
      resp_pulsante = supabase.table("IlMioPulsante").select("*").eq("user_id", st.session_state.user.id).execute()
      salvati_pulsante = resp_pulsante.data if resp_pulsante and resp_pulsante.data else []

      with st.form("form_gestione_pulsante"):
        st.subheader("Configura il tuo controller")
        p_nome = st.text_input("Nome Configurazione Pulsante", value=st.session_state.get("modifying_pulsante_data", {}).get("nome", ""))
        p_curva = st.selectbox("Curva di Erogazione", ["Lineare", "Aggressiva", "Dolce", "Personalizzata"])
        p_frenata = st.slider("Sensibilità Frenata", 1, 10, 5)
        p_grilletto = st.slider("Corsa del Grilletto", 1, 10, 5)
        p_note = st.text_area("Note sul Pulsante", value=st.session_state.get("modifying_pulsante_data", {}).get("note", ""))

        submit_pulsante = st.form_submit_button("Salva Configurazione Pulsante")
        if submit_pulsante:
          dati_pulsante = {
              "nome": p_nome,
              "curva": p_curva,
              "frenata": p_frenata,
              "grilletto": p_grilletto,
              "note": p_note,
              "user_id": st.session_state.user.id
          }
          if st.session_state.modifying_pulsante_id:
            supabase.table("IlMioPulsante").update(dati_pulsante).eq("id", st.session_state.modifying_pulsante_id).execute()
            st.success("Configurazione pulsante aggiornata!")
            st.session_state.modifying_pulsante_id = None
            st.session_state.modifying_pulsante_data = None
          else:
            supabase.table("IlMioPulsante").insert(dati_pulsante).execute()
            st.success("Configurazione pulsante salvata!")
          st.rerun()

      if salvati_pulsante:
        st.divider()
        st.subheader("I tuoi setup pulsante salvati")
        for p_item in salvati_pulsante:
          with st.expander(f"🎛️ {p_item.get('nome')} (Curva: {p_item.get('curva')})"):
            st.json(p_item)
            if st.button("Elimina Setup Pulsante", key=f"del_p_{p_item.get('id')}"):
              supabase.table("IlMioPulsante").delete().eq("id", p_item.get("id")).execute()
              st.rerun()

    except Exception as e:
      st.error(f"Errore nella sezione Il Mio Pulsante: {e}")

elif st.session_state.active_tab == "➕ Carica Modello":
  st.header("➕ Carica Nuovo Modello")
  if not st.session_state.user:
    st.warning("⚠️ Effettua l'accesso per poter caricare un nuovo modello nel sistema.")
    richiedi_autenticazione()
  else:
    with st.form("form_carica_nuovo_modello"):
      nuovo_modello = st.text_input("Nome del Modello")
      carica_file_foto = st.file_uploader("Carica Foto Modello", type=["jpg", "jpeg", "png"])
      foto_modello_url = st.text_input("O inserisci URL Immagine Modello")

      prod_form_list = {
          p.get("name"): p.get("id")
          for p in produttori
          if p and p.get("name") and p.get("id")
      }
      cat_form_list = {
          c.get("name"): c.get("id")
          for c in categorie
          if c and c.get("name") and c.get("id")
      }

      scelta_produttore = st.selectbox(
          "Produttore", list(prod_form_list.keys()) if prod_form_list else []
      )
      scelta_categoria = st.selectbox(
          "Categoria", list(cat_form_list.keys()) if cat_form_list else []
      )

      submitted = st.form_submit_button("Salva nel Database")

      if submitted:
        if not nuovo_modello:
          st.error("Inserisci il nome del modello.")
        else:
          try:
            finale_foto_url = foto_modello_url
            if carica_file_foto is not None:
              uploaded_cloud_url = upload_image_to_supabase(carica_file_foto)
              if uploaded_cloud_url:
                finale_foto_url = uploaded_cloud_url

            id_cat_scelta = cat_form_list.get(scelta_categoria)
            nuovo_record = {
                "name": nuovo_modello,
                "category_id": id_cat_scelta,
                "foto_url": finale_foto_url
            }
            supabase.table("MODELLI").insert(nuovo_record).execute()
            st.success(f"Modello '{nuvo_modello if 'nuvo_modello' in locals() else nuovo_modello}' caricato con successo!")
            st.cache_data.clear()
            st.rerun()
          except Exception as e:
            st.error(f"Errore durante il caricamento del modello: {e}")
