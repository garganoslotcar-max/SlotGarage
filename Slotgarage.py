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
TITOLO_PATH = "titolo.png" # Il nome del file per il titolo

st.set_page_config(page_title="SlotGarage", page_icon=LOGO_PATH, layout="wide")

# --- INTESTAZIONE CON LOGO E TITOLO IN PNG ---
col_logo, col_titolo = st.columns([2, 10])
with col_logo:
  try:
    st.image(LOGO_PATH, width=220)
  except Exception:
    st.write("🏎️")
with col_titolo:
  try:
    st.image(TITOLO_PATH, width=500) # Regola la larghezza qui
    st.markdown(
        "<p style='color: #FFD700; font-size: 1.3rem; margin-top: -10px; margin-left: 10px;'>"
        "Creato da Emanuele Palena</p>",
        unsafe_allow_html=True,
    )
  except Exception:
    st.markdown(
        "<h1 style='margin-top: 25px; font-size: 4.2rem;'>SlotGarage</h1>",
        unsafe_allow_html=True,
    )

if not supabase:
  st.error("Errore di connessione a Supabase.")
  st.stop()

# --- TUTTO IL RESTO DEL CODICE RIMANE INALTERATO ---
# (Il caricamento dati, stato, navigazione e funzioni restano identici)
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

# ... [IL RESTO DEL TUO CODICE PROSEGUE QUI COME DA FILE ORIGINALE] ...