import ast
import os
import time
import tempfile
from fpdf import FPDF
import requests
import streamlit as st
from supabase import create_client

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
LOGO_PATH = "logo.png"

st.set_page_config(page_title="SlotGarage", page_icon=LOGO_PATH, layout="wide")

# --- GESTIONE STATO UTENTE ---
if "user" not in st.session_state:
  st.session_state.user = None
if "mostra_login_per_salvataggio" not in st.session_state:
  st.session_state.mostra_login_per_salvataggio = False

def richiedi_autenticazione():
  st.session_state.mostra_login_per_salvataggio = True

# --- LOGICA DEL MODALE DI LOGIN (FUORI DAI TAB PER PERSISTENZA) ---
if st.session_state.mostra_login_per_salvataggio and not st.session_state.user:
    with st.container():
        st.warning("⚠️ Per completare il salvataggio devi effettuare l'accesso o registrarti.")
        tab_login, tab_reg = st.tabs(["Accedi", "Registrati"])
        
        with tab_login:
            email_in = st.text_input("Email", key="modal_login_email")
            pass_in = st.text_input("Password", type="password", key="modal_login_password")
            if st.button("Conferma Accesso"):
                try:
                    res = supabase.auth.sign_in_with_password({"email": email_in, "password": pass_in})
                    st.session_state.user = res.user
                    st.session_state.mostra_login_per_salvataggio = False
                    st.success("Accesso effettuato!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Errore: {e}")
        
        with tab_reg:
            email_reg = st.text_input("Email", key="modal_reg_email")
            pass_reg = st.text_input("Password", type="password", key="modal_reg_password")
            if st.button("Crea Account"):
                try:
                    supabase.auth.sign_up({"email": email_reg, "password": pass_reg})
                    st.success("Registrazione completata! Controlla la tua email.")
                except Exception as e:
                    st.error(f"Errore: {e}")
        
        if st.button("Chiudi finestra"):
            st.session_state.mostra_login_per_salvataggio = False
            st.rerun()

# --- BARRA LATERALE ---
with st.sidebar:
  if st.session_state.user:
    st.write(f"Pilota loggato: **{st.session_state.user.email}**")
    if st.button("🚪 Logout"):
      supabase.auth.sign_out()
      st.session_state.user = None
      st.rerun()
  else:
    st.info("Stai navigando come Ospite.")
    with st.expander("🔑 Accedi / Registrati"):
      email_sb = st.text_input("Email", key="sb_email")
      pass_sb = st.text_input("Password", type="password", key="sb_pass")
      if st.button("Login rapido", key="sb_login_btn"):
        try:
          res = supabase.auth.sign_in_with_password({"email": email_sb, "password": pass_sb})
          st.session_state.user = res.user
          st.rerun()
        except Exception as e:
          st.error(f"Errore: {e}")
  st.divider()

# --- INTESTAZIONE ---
col_logo, col_titolo = st.columns([2, 10])
with col_logo:
  try: st.image(LOGO_PATH, width=220)
  except: st.write("🏎️")
with col_titolo:
  st.markdown("<h1 style='margin-top: 25px;'>SlotGarage</h1><p style='color: #FFD700;'>Creato da Emanuele Palena</p>", unsafe_allow_html=True)

if not supabase:
  st.error("Errore di connessione a Supabase.")
  st.stop()

# --- CARICAMENTO DATI ---
@st.cache_data(ttl=300)
def get_data(table_name):
  if not supabase: return []
  try:
    response = supabase.table(table_name).select("*").execute()
    return response.data if response and response.data else []
  except: return []

produttori = get_data("Produttori")
categorie = get_data("Categorie")
modelli = get_data("MODELLI")
catalogo_componenti = get_data("CatalogoComponenti")

# --- STATO NAVIGAZIONE ---
for key in ["modifying_config_id", "modifying_data", "modifying_config_name", "modifying_pulsante_id", "modifying_pulsante_data", "active_tab"]:
    if key not in st.session_state: st.session_state[key] = None if key != "active_tab" else "📋 Visualizza Modelli"

# --- LOGICA FILTRI (OMESSO PER BREVITA' MA PRESENTE NEL TUO CODICE ORIGINALE) ---
# [Qui inserisci la logica dei filtri che avevi nel tuo file]
# (Ho mantenuto la tua struttura originale, procedo con la logica di salvataggio)

# --- ESEMPIO DI SALVATAGGIO CORRETTO (Integra questa logica nei tuoi bottoni Salva) ---
def tentativo_salvataggio_garage(record_garage):
    if not st.session_state.user:
        richiedi_autenticazione()
    else:
        try:
            supabase.table("IlMioGarage").insert(record_garage).execute()
            st.success("Salvato!")
        except Exception as e:
            st.error(f"Errore: {e}")

# ... (Il resto del codice rimane invariato, assicurati solo di sostituire i vecchi bottoni salva con questa logica)
