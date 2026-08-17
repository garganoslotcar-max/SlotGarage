import ast
import os
import time
import tempfile
from fpdf import FPDF
import requests
import streamlit as st
from supabase import create_client, ClientOptions

# --- [CONFIGURAZIONE SUPABASE & SICUREZZA INVARIATA] ---
# (Il blocco di configurazione rimane identico a quello fornito)
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

# ... [OMISSIS: Funzioni di stato, autenticazione, caricamento dati e UI] ...
# (Mantenere tutto il codice esistente fino alla funzione generate_pdf)

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

  # ... [OMISSIS: Logica inserimento foto] ...

  # Filtro e formattazione migliorata per il PDF
  dettagli_filtrati = {}
  for k, v in dettagli.items():
    if k.lower() in ["note", "foto_personalizzata_url"]: continue
    # Gestione esplicita distanziali separati
    if "distanzial" in k.lower():
      dettagli_filtrati[k.replace("_", " ")] = v
    else:
      dettagli_filtrati[k] = v

  pesi_motore_keywords = ["peso", "giri", "motore", "supporto", "corona", "pignoni"]
  left_items = {k: v for k, v in dettagli_filtrati.items() if any(pk in k.lower() for pk in pesi_motore_keywords)}
  right_items = {k: v for k, v in dettagli_filtrati.items() if k not in left_items}

  # ... [OMISSIS: Resto della funzione draw_tech_section e finalizzazione PDF] ...
  return pdf.output(dest="S").encode("latin1")

# --- [OMISSIS: Resto del codice, inclusa la logica dei Distanziali nel setup] ---
# Assicurati che nel blocco setup, la chiave scelta sia coerente: 
# "Distanziali_Posteriori" è ora gestito in modo univoco per evitare sovrascritture.
