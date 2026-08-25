import ast
import json
import os
import time
import tempfile
import streamlit as st
import json
import os
import re
import unicodedata
from urllib.parse import urlparse
from fpdf import FPDF
import requests
import streamlit as st
from datetime import datetime, date
from supabase import create_client, ClientOptions
import csv

# --- CONFIGURAZIONE SUPABASE & SICUREZZA ---
try:
  SUPABASE_URL = st.secrets["supabase"]["url"]
  SUPABASE_KEY = st.secrets["supabase"]["key"]
except Exception:
  st.error("❌ Configurazione Supabase mancante. Imposta st.secrets.")
  st.stop()

def init_connection():
  client = st.session_state.get("_supabase_client")
  if client is not None:
    return client
  try:
    options = ClientOptions(persist_session=True)
    client = create_client(SUPABASE_URL, SUPABASE_KEY, options=options)
    st.session_state["_supabase_client"] = client
    return client
  except Exception as e:
    st.error(f"Errore di connessione a Supabase: {e}")
    return None

supabase = init_connection()

LOGO_PATH = "logo.png"


# ===== SLOTGARAGE PRO V5 =====
def sg_parse_dict(value):
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    if isinstance(value, str):
        try:
            obj = json.loads(value)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
        try:
            obj = ast.literal_eval(value)
            return obj if isinstance(obj, dict) else {}
        except (ValueError, SyntaxError, TypeError):
            return {"raw": value}
    return {}

def sg_config_label(row):
    nome = row.get("nome_configurazione") or row.get("nome") or "Senza nome"
    modello = row.get("modello") or row.get("modello_nome") or ""
    return f"{nome} — {modello}".strip(" —")

def sg_flatten(row):
    out = {}
    for k, v in (row or {}).items():
        if k in {"id", "user_id", "created_at", "updated_at"}:
            continue
        parsed = sg_parse_dict(v)
        if parsed and isinstance(v, (dict, str)):
            for sk, sv in parsed.items():
                out[f"{k}.{sk}"] = sv
        else:
            out[k] = v
    return out

def sg_compare(a, b):
    aa, bb = sg_flatten(a), sg_flatten(b)
    diffs = []
    for key in sorted(set(aa) | set(bb), key=str.lower):
        av = str(aa.get(key, "—")).strip()
        bv = str(bb.get(key, "—")).strip()
        if av.casefold() != bv.casefold():
            diffs.append({"Parametro": key, "A": av, "B": bv})
    return diffs

def sg_seconds(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(str(value).lower().replace("s", "").replace(",", ".").strip())
    except (ValueError, TypeError):
        return None

def sg_load_garage():
    try:
        uid = sg_current_user_id()
        return supabase.table("IlMioGarage").select("*").eq("user_id", uid).execute().data or []
    except Exception:
        return []

def sg_pro_ui():
    if not st.session_state.get("user"):
        return

    st.markdown("---")
    st.subheader("Comparazione e Telemetria Modelli")

    tabs = st.tabs([
        "Confronto configurazioni",
        "Prove in pista",
        "Storico modifiche",
        "Classifica prestazioni",
        "Archivio componenti",
        "Analisi modifica",
    ])

    garage = sg_load_garage()

    with tabs[0]:
        if len(garage) < 2:
            st.info("Servono almeno due configurazioni salvate nel Garage.")
        else:
            labels = [sg_config_label(r) for r in garage]
            a_i = st.selectbox("Configurazione A", range(len(garage)),
                               format_func=lambda i: labels[i], key="pro5_cmp_a")
            b_i = st.selectbox("Configurazione B", range(len(garage)),
                               index=min(1, len(garage)-1),
                               format_func=lambda i: labels[i], key="pro5_cmp_b")
            if a_i == b_i:
                st.warning("Seleziona due configurazioni diverse.")
            else:
                diffs = sg_compare(garage[a_i], garage[b_i])
                if diffs:
                    st.dataframe(diffs, use_container_width=True, hide_index=True)
                else:
                    st.success("Nessuna differenza rilevata.")

    with tabs[1]:
        if not garage:
            st.info("Salva prima una configurazione nel Garage.")
        else:
            labels = [sg_config_label(r) for r in garage]
            ci = st.selectbox("Configurazione", range(len(garage)),
                              format_func=lambda i: labels[i], key="pro5_test_cfg")
            c1, c2 = st.columns(2)
            with c1:
                pista = st.text_input("Pista", key="pro5_test_track")
                data_prova = st.date_input("Data", value=date.today(), key="pro5_test_date")
                giri = st.number_input("Giri", min_value=0, value=50, step=1, key="pro5_test_laps")
                corsia = st.text_input("Corsia", key="pro5_test_lane")
            with c2:
                best = st.text_input("Miglior tempo (s)", placeholder="8.423", key="pro5_test_best")
                media = st.text_input("Tempo medio (s)", placeholder="8.691", key="pro5_test_avg")
                pneumatici = st.text_input("Pneumatici", key="pro5_test_tires")
                note = st.text_input("Note", key="pro5_test_notes")
            if st.button("Salva prova in pista", type="primary", key="pro5_test_save"):
                best_s = sg_seconds(best)
                if not pista.strip() or best_s is None:
                    st.warning("Inserisci una pista e un miglior tempo valido.")
                else:
                    payload = {
                        "user_id": st.session_state.user.id,
                        "garage_id": garage[ci].get("id"),
                        "modello": garage[ci].get("modello"),
                        "configurazione": garage[ci].get("nome_configurazione") or garage[ci].get("nome"),
                        "pista": pista.strip(),
                        "data_prova": str(data_prova),
                        "giri": int(giri),
                        "miglior_tempo": best_s,
                        "tempo_medio": sg_seconds(media),
                        "corsia": corsia.strip(),
                        "pneumatici": pneumatici.strip(),
                        "note": note.strip(),
                    }
                    try:
                        sg_save_telemetry_test(payload)
                        st.success("Prova salvata.")
                    except Exception as e:
                        st.error(f"Errore salvataggio prova: {e}")

            try:
                tests = sg_load_telemetry_tests(sg_current_user_id())
            except Exception:
                tests = []
            if tests:
                st.dataframe([{
                    "Configurazione": t.get("configurazione"),
                    "Pista": t.get("pista"),
                    "Data": t.get("data_prova"),
                    "Giri": t.get("giri"),
                    "Miglior tempo": f"{t.get('miglior_tempo'):.3f} s" if t.get('miglior_tempo') is not None else "—",
                    "Media": f"{t.get('tempo_medio'):.3f} s" if t.get('tempo_medio') is not None else "—",
                    "Pneumatici": t.get("pneumatici"),
                } for t in tests], use_container_width=True, hide_index=True)

    with tabs[2]:
        if len(garage) < 2:
            st.info("Servono almeno due configurazioni per generare uno storico.")
        else:
            labels = [sg_config_label(r) for r in garage]
            old_i = st.selectbox("Versione precedente", range(len(garage)),
                                 format_func=lambda i: labels[i], key="pro5_hist_old")
            new_i = st.selectbox("Versione successiva", range(len(garage)),
                                 index=min(1, len(garage)-1),
                                 format_func=lambda i: labels[i], key="pro5_hist_new")
            if old_i != new_i:
                diffs = sg_compare(garage[old_i], garage[new_i])
                if diffs:
                    st.dataframe(diffs, use_container_width=True, hide_index=True)
                    if st.button("Salva storico modifica", key="pro5_hist_save"):
                        try:
                            sg_save_telemetry_history({
                                "user_id": st.session_state.user.id,
                                "garage_id": garage[new_i].get("id"),
                                "vecchio_garage_id": garage[old_i].get("id"),
                                "data_modifica": datetime.now().isoformat(),
                                "modifiche": json.dumps(diffs, ensure_ascii=False),
                            }).execute()
                            st.success("Storico salvato.")
                        except Exception as e:
                            st.error(f"Errore salvataggio storico: {e}")
                else:
                    st.info("Nessuna differenza rilevata.")

    with tabs[3]:
        st.caption("Confronta i migliori tempi registrati per capire quali configurazioni rendono meglio in pista.")
        try:
            tests = sg_load_telemetry_tests(sg_current_user_id())
        except Exception:
            tests = []
        if not tests:
            st.info("Nessuna prova in pista registrata.")
        else:
            best_by_cfg = {}
            for t in tests:
                key = (t.get("modello") or "", t.get("configurazione") or "")
                tm = t.get("miglior_tempo")
                if tm is not None and (key not in best_by_cfg or tm < best_by_cfg[key]):
                    best_by_cfg[key] = tm
            ranking = sorted(
                [{"Pos.": i+1, "Modello": k[0], "Configurazione": k[1],
                  "Miglior tempo": f"{v:.3f} s"}
                 for i, (k, v) in enumerate(best_by_cfg.items())],
                key=lambda x: x["Miglior tempo"]
            )
            for i, row in enumerate(ranking, 1):
                row["Pos."] = i
            st.dataframe(ranking, use_container_width=True, hide_index=True)

    with tabs[4]:
        st.caption("Archivio personale di motori, corone, pignoni, cerchi, pneumatici e sospensioni, da collegare alle preparazioni.")
        c1, c2 = st.columns(2)
        with c1:
            tipo = st.selectbox("Tipo componente",
                                ["Motore", "Corona", "Pignone", "Cerchi",
                                 "Pneumatici", "Sospensioni", "Altro"],
                                key="pro5_comp_type")
            marca = st.text_input("Marca", key="pro5_comp_brand")
        with c2:
            nome = st.text_input("Nome / codice", key="pro5_comp_name")
            note = st.text_input("Note", key="pro5_comp_notes")
        if st.button("Salva componente", type="primary", key="pro5_comp_save"):
            if not nome.strip():
                st.warning("Inserisci nome o codice.")
            else:
                try:
                    sg_save_telemetry_component({
                        "user_id": st.session_state.user.id,
                        "tipo": tipo,
                        "marca": marca.strip(),
                        "nome": nome.strip(),
                        "note": note.strip(),
                    }).execute()
                    st.success("Componente salvato.")
                except Exception as e:
                    st.error(f"Errore salvataggio componente: {e}")
        try:
            components = sg_load_telemetry_components(sg_current_user_id())
        except Exception:
            components = []
        if components:
            st.dataframe([{
                "Tipo": x.get("tipo"), "Marca": x.get("marca"),
                "Nome / codice": x.get("nome"), "Note": x.get("note")
            } for x in components], use_container_width=True, hide_index=True)

    # ============================================================
    # TAB 5 - CALCOLATORE RAPPORTI (NUOVO)
    # ============================================================
    with tabs[5]:
        st.caption("Calcola il rapporto di trasmissione e simula l'effetto di una modifica.")
        
        if garage:
            cfg_idx = st.selectbox("Seleziona configurazione da analizzare", range(len(garage)),
                                   format_func=lambda i: sg_config_label(garage[i]), key="rapp_cfg")
            cfg = garage[cfg_idx] if cfg_idx is not None else None
            dettagli = deserialize_details(cfg.get("dettagli_setup", {})) if cfg else {}
            
            # Estrai valori attuali
            corona_attuale = dettagli.get("Corona", "")
            pignone_attuale = dettagli.get("Pignoni", "")
            giri_motore = dettagli.get("Giri_Motore", "")
            
            import re
            def estrai_denti(testo):
                if not testo:
                    return None
                numeri = re.findall(r'\d+', str(testo))
                if numeri:
                    for n in numeri:
                        val = int(n)
                        if 20 <= val <= 40:
                            return val
                        elif 8 <= val <= 15:
                            return val
                return None
            
            corona_denti = estrai_denti(corona_attuale)
            pignone_denti = estrai_denti(pignone_attuale)
            
            col_r1, col_r2 = st.columns(2)
            with col_r1:
                st.markdown("**📐 Setup attuale**")
                corona_input = st.text_input("Corona (denti)", value=str(corona_denti) if corona_denti else "", key="rapp_corona_att")
                pignone_input = st.text_input("Pignone (denti)", value=str(pignone_denti) if pignone_denti else "", key="rapp_pignone_att")
                giri_input = st.text_input("Giri motore (rpm)", value=giri_motore if giri_motore else "", key="rapp_giri")
            
            with col_r2:
                st.markdown("**🔄 Simula modifica**")
                corona_nuova = st.text_input("Nuova corona (denti)", value="", key="rapp_corona_nuova")
                pignone_nuovo = st.text_input("Nuovo pignone (denti)", value="", key="rapp_pignone_nuovo")
            
            try:
                c_att = int(corona_input) if corona_input.strip().isdigit() else None
                p_att = int(pignone_input) if pignone_input.strip().isdigit() else None
                c_nuo = int(corona_nuova) if corona_nuova.strip().isdigit() else None
                p_nuo = int(pignone_nuovo) if pignone_nuovo.strip().isdigit() else None
                
                if c_att and p_att:
                    rapporto_att = c_att / p_att
                    st.metric("📐 Rapporto attuale", f"{rapporto_att:.2f} ({c_att}/{p_att})")
                
                if c_nuo and p_nuo:
                    rapporto_nuo = c_nuo / p_nuo
                    st.metric("📐 Rapporto nuovo", f"{rapporto_nuo:.2f} ({c_nuo}/{p_nuo})")
                    
                    if c_att and p_att:
                        diff = ((rapporto_nuo - rapporto_att) / rapporto_att) * 100
                        if diff > 0:
                            st.success(f"📈 Rapporto più alto del {diff:.1f}% → **Più accelerazione**")
                        elif diff < 0:
                            st.success(f"📉 Rapporto più basso del {abs(diff):.1f}% → **Più velocità**")
                        else:
                            st.info("ℹ️ Rapporto invariato")
                
                if c_att and p_att and giri_input.strip().isdigit():
                    giri = int(giri_input)
                    rapporto = c_att / p_att if c_att and p_att else 1
                    circonferenza = 0.066
                    velocita = (giri / rapporto) * circonferenza * 60 / 1000
                    st.metric("🚀 Velocità stimata", f"{velocita:.1f} km/h")
                    
            except Exception as e:
                st.warning(f"Inserisci numeri validi per corona e pignone.")
        else:
            st.info("Salva prima una configurazione nel Garage per analizzarla.")



# ===== SLOTGARAGE V8 REFACTOR HELPERS =====
def sg_current_user_id():
    user = st.session_state.get("user")
    return getattr(user, "id", None) if user else None

def sg_db_select(table, *, user_id=None, order_column=None, desc=False):
    try:
        query = supabase.table(table).select("*")
        if user_id is not None:
            query = query.eq("user_id", user_id)
        if order_column:
            query = query.order(order_column, desc=desc)
        return query.execute().data or []
    except Exception as e:
        st.warning(f"Errore durante la lettura da {table}: {e}")
        return []

def sg_db_insert(table, payload):
    try:
        return supabase.table(table).insert(payload).execute().data or []
    except Exception as e:
        st.error(f"Errore durante l'inserimento in {table}: {e}")
        return []

def sg_load_telemetry_tests(user_id=None):
    return sg_db_select(
        "SlotGarage_Prove",
        user_id=user_id,
        order_column="miglior_tempo",
        desc=False,
    )

def sg_load_telemetry_components(user_id=None):
    return sg_db_select(
        "SlotGarage_Componenti",
        user_id=user_id,
        order_column="created_at",
        desc=True,
    )

def sg_load_telemetry_history(user_id=None):
    return sg_db_select(
        "SlotGarage_Storico",
        user_id=user_id,
        order_column="data_modifica",
        desc=True,
    )

def sg_save_telemetry_test(payload):
    return sg_db_insert("SlotGarage_Prove", payload)

def sg_save_telemetry_component(payload):
    return sg_db_insert("SlotGarage_Componenti", payload)

def sg_save_telemetry_history(payload):
    return sg_db_insert("SlotGarage_Storico", payload)

def sg_safe_message(action, exc):
    return f"Errore durante {action}: {exc}"

st.set_page_config(page_title="SlotGarage", page_icon=LOGO_PATH, layout="wide")

# --- GESTIONE STATO UTENTE & PERSISTENZA SESSIONE ---
if "user" not in st.session_state:
  if supabase and supabase.auth.get_session():
    st.session_state.user = supabase.auth.get_session().user
  else:
    st.session_state.user = None

if "pending_garage_data" not in st.session_state:
  st.session_state.pending_garage_data = None

if "regolamento_dati" not in st.session_state:
    st.session_state.regolamento_dati = {}
if "regolamento_attivo" not in st.session_state:
    st.session_state.regolamento_attivo = False

def serialize_details(value):
  if isinstance(value, str):
    return value
  return json.dumps(value or {}, ensure_ascii=False, separators=(",", ":"))

def deserialize_details(value):
    if isinstance(value, dict):
        return value
    if value is None or value == "":
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {"Dettagli": parsed}
        except (json.JSONDecodeError, TypeError):
            try:
                parsed = ast.literal_eval(value)
                return parsed if isinstance(parsed, dict) else {"Dettagli": parsed}
            except (ValueError, SyntaxError, TypeError):
                return {"Dettagli": value}
    return {"Dettagli": value}

def clear_garage_edit_state():
  for key, value in {
      "modifying_config_id": None,
      "modifying_data": None,
      "modifying_config_name": "",
      "modifying_model_name": None,
  }.items():
    st.session_state[key] = value

def process_pending_garage():
    pending = st.session_state.get("pending_garage_data")
    user = st.session_state.get("user")
    if not pending or not user or supabase is None:
        return

    nome = str(pending.get("nome_configurazione") or "").strip()
    modello = str(pending.get("modello_nome") or "").strip()
    if not nome or not modello:
        st.warning("Nome o modello mancanti per il salvataggio.")
        st.session_state.pending_garage_data = None
        st.session_state.active_tab = "🚗 Il Mio Garage"
        return

    try:
        dettagli_pending = pending.get("dettagli_setup", {})
        telaio_catalogo_id = trova_telaio_catalogo_id(
            dettagli_pending.get("Telaio") if isinstance(dettagli_pending, dict) else None
        )

        record_garage = {
            "nome_configurazione": nome,
            "modello_nome": modello,
            "dettagli_setup": serialize_details(dettagli_pending),
            "telaio_catalogo_id": telaio_catalogo_id,
            "user_id": user.id,
        }
        if pending.get("is_update"):
            supabase.table("IlMioGarage").update(record_garage).eq(
                "id", pending.get("config_id")
            ).eq("user_id", user.id).execute()
            st.success(f"Configurazione '{nome}' aggiornata con successo dopo il login!")
            clear_garage_edit_state()
        else:
            supabase.table("IlMioGarage").insert(record_garage).execute()
            st.success(f"Configurazione '{nome}' salvata con successo nel tuo Garage dopo il login!")

    except Exception as e:
        st.error(f"Errore durante il salvataggio post-login: {e}")
    finally:
        st.session_state.pending_garage_data = None
        st.session_state.active_tab = "🚗 Il Mio Garage"
        st.rerun()

process_pending_garage()

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

    with st.expander("📝 Registrati"):
      with st.form("sb_reg_form_definitivo"):
        email_reg_sb = st.text_input("Email", key="sb_reg_email_def")
        pass_reg_sb = st.text_input("Password", type="password", key="sb_reg_password_def")
        if st.form_submit_button("Crea Account", key="sb_reg_btn_def"):
          try:
            supabase.auth.sign_up({"email": email_reg_sb, "password": pass_reg_sb})
            st.success("Registrazione completata! Ora puoi effettuare il login.")
          except Exception as e:
            st.error(f"Errore durante la registrazione: {e}")
  st.divider()

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


def trova_telaio_catalogo_id(telaio):
    if not telaio:
        return None

    valore = str(telaio).strip().casefold()

    for componente in catalogo_componenti or []:
        if not componente:
            continue
        if str(componente.get("Prodotto") or "").strip().casefold() != "telaio":
            continue

        materiale = str(componente.get("Materiale") or "").strip()
        misure = str(componente.get("Misure") or "").strip()
        nome_catalogo = f"{materiale} - {misure}" if materiale and misure else (materiale or misure)

        if nome_catalogo.strip().casefold() == valore:
            return componente.get("id")

    return None

if not produttori and not modelli:
  st.warning(
      "Connessione al cloud in corso o database temporaneamente in standby..."
  )
  if st.button("🔄 Riprova Connessione"):
    st.cache_data.clear()
    st.rerun()

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
if "configura_regolamento_target" not in st.session_state:
  st.session_state.configura_regolamento_target = None

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
      "Scegli Marchio", prod_names_list, index=default_prod_idx
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
      "Scegli Categoria", cat_names_list, index=default_cat_idx
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
  selected_model_name = st.selectbox("Modello", mod_names_list, index=default_mod_idx)

st.divider()

tabs_list = [
    "📋 Visualizza Modelli",
    "🚗 Il Mio Garage",
    "🎛️ Il Mio Pulsante",
    "➕ Carica Modello",
    "Comparazione e Telemetria Modelli",
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


def _boxstock_normalize(value):
    if value is None:
        return ""
    s = str(value).strip().lower()
    s = s.replace("–", "-").replace("—", "-").replace("’", "'")
    s = re.sub(r"\\s+", " ", s)
    s = re.sub(r"\\s*-\\s*", "-", s)
    return s

def _boxstock_exact_index(options, target):
    nt = _boxstock_normalize(target)
    if not nt:
        return None
    normalized = [_boxstock_normalize(x) for x in options]
    for i, value in enumerate(normalized):
        if value == nt:
            return i
    words = [w for w in re.split(r"[^a-z0-9.]+", nt) if len(w) > 1]
    if words:
        candidates = []
        for i, value in enumerate(normalized):
            if all(w in value for w in words):
                candidates.append(i)
        if len(candidates) == 1:
            return candidates[0]
    return None

def find_default_index(opzioni, model_name, target_value=None):
    if not opzioni:
        return None

    def _match_key(v):
        import re, unicodedata
        t = str(v or "").strip().casefold()
        t = unicodedata.normalize("NFKD", t)
        t = "".join(ch for ch in t if not unicodedata.combining(ch))
        return re.sub(r"[^a-z0-9]+", "", t)

    if target_value:
        target_key = _match_key(target_value)
        for idx, opt in enumerate(opzioni):
            if _match_key(opt) == target_key:
                return idx
        parole = [w for w in re.findall(r"[a-z0-9]+", target_key) if len(w) >= 2]
        if parole:
            candidati = [idx for idx, opt in enumerate(opzioni)
                         if all(p in _match_key(opt) for p in parole)]
            if len(candidati) == 1:
                return candidati[0]

    if model_name and model_name != "Tutti":
        model_key = _match_key(model_name)
        for idx, opt in enumerate(opzioni):
            if model_key in _match_key(opt):
                return idx
        parole = [w for w in re.findall(r"[a-z0-9]+", model_key) if len(w) > 2]
        if parole:
            candidati = [idx for idx, opt in enumerate(opzioni)
                         if all(p in _match_key(opt) for p in parole)]
            if len(candidati) == 1:
                return candidati[0]

    return 0 if opzioni else None

def _boxstock_target(produttore, categoria, campo):
  def _norm(v):
    import unicodedata
    t = str(v or "").strip().casefold()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = t.replace("-", " ").replace("_", " ")
    return " ".join(t.split())

  p = _norm(produttore)
  c = _norm(categoria)
  f = _norm(campo)

  defaults = {
    ("nsr", "gt3", "motore"): "King - Evo3 - 21.400 rpm - Standard",
    ("nsr", "gt3", "supporto motore"): "Anglewinder - Evo - Extra Hard (Rosso)",
    ("nsr", "gt3", "corona"): "Anglewinder Alluminio - 31 denti 17.5mm",
    ("nsr", "gt3", "pignoni"): "Anglewinder - 13 denti - 7.5m",
    ("nsr", "gt3", "assale anteriore"): '3/32" - Standard - Acciaio Rettificato - 55mm',
    ("nsr", "gt3", "assale posteriore"): '3/32" - Standard - Acciaio Rettificato - 55mm',
    ("nsr", "gt3", "cerchi anteriori"): "Cerchi Anteriori Grandi No Air System da 17.25x8.2mm",
    ("nsr", "gt3", "cerchi posteriori"): "Posteriori - Alluminio - No Air System - Standard - 17x8mm",
    ("nsr", "gt3", "forcella"): "1234",
    ("nsr", "gt3", "gomme anteriori"): "NSR 5200 16x8",
    ("nsr", "gt3", "gomme posteriori"): "NSR 5279Z 19.5x11",

    ("nsr", "hypercar", "motore"): "King - Evo3 - 21.400 rpm - Standard",
    ("nsr", "hypercar", "supporto motore"): "NSR HYPERCAR - ExtraHard Rosso Sidewinder Offset - 1M",
    ("nsr", "hypercar", "corona"): "Sidewinder Alluminio - 31 denti 16.8 mm",
    ("nsr", "hypercar", "pignoni"): "Anglewinder - 13 denti - 7.5m",
    ("nsr", "hypercar", "assale anteriore"): '3/32" - Standard - Acciaio Rettificato - 55mm',
    ("nsr", "hypercar", "assale posteriore"): '3/32" - Standard - Acciaio Rettificato - 55mm',
    ("nsr", "hypercar", "cerchi anteriori"): "Anteriori Grandi No Air System da 17.25x8mm",
    ("nsr", "hypercar", "cerchi posteriori"): "Posteriori Grandi Air System da 17.25x10mm",
    ("nsr", "hypercar", "gomme anteriori"): "NSR 5200 16x8",
    ("nsr", "hypercar", "gomme posteriori"): "NSR 5266Z 20x11",

    ("nsr", "f1 22", "motore"): "King - Evo3 - 21.400 rpm - Standard",
    ("nsr", "f1 22", "supporto motore"): "in linea - NSR Formula 22 - Standard Medium Nero",
    ("nsr", "f1 22", "corona"): "in Linea Evo Nera - 27 denti",
    ("nsr", "f1 22", "pignoni"): "in linea - NSR Formula 22 - 10 denti - Ottone",
    ("nsr", "f1 22", "assale anteriore"): '3/32" - Standard - Acciaio Rettificato - 55mm',
    ("nsr", "f1 22", "assale posteriore"): '3/32" - Standard - Acciaio Rettificato - 55mm',
    ("nsr", "f1 22", "cerchi anteriori"): "Cerchi Anteriori 16.5x8mm NO-AIR System",
    ("nsr", "f1 22", "cerchi posteriori"): "Posteriori - Alluminio - Air System - Standard - 16x8mm",
    ("nsr", "f1 22", "gomme anteriori"): "NSR 5296N 19.5x9.5",
    ("nsr", "f1 22", "gomme posteriori"): "NSR 5294Z 19x13",

    ("nsr", "classic", "motore"): "Shark - Evo 21.500 rpm - Standard",
    ("nsr", "classic", "supporto motore"): "Sidewinder - Evo - Extra Hard (Rosso)",
    ("nsr", "classic", "corona"): "Sidewinder Alluminio - 32 denti 17.5mm",
    ("nsr", "classic", "pignoni"): "Sidewinder - Ottone - 11 denti - 6.5mm",
    ("nsr", "classic", "assale anteriore"): '3/32" - Standard Acciaio Rettificato - 49mm',
    ("nsr", "classic", "assale posteriore"): '3/32" - Standard Acciaio Rettificato - 49mm',
    ("nsr", "classic", "cerchi anteriori"): "Anteriori - Alluminio - No Air System - Standard - 16x8mm",
    ("nsr", "classic", "cerchi posteriori"): "Posteriori - Alluminio - Air System - Standard - 16x8mm",
    ("nsr", "classic", "pickup"): "Standard - Lama corta",
    ("nsr", "classic", "dettaglio supporto"): 'Bronzine Standard da 3/32"',
    ("nsr", "classic", "gomme anteriori"): "NSR 5200 16x8",
    ("nsr", "classic", "gomme posteriori"): "NSR 5271WRE 19.5x11",

    ("nsr", "mosler", "motore"): "King - Evo3 - 21.400 rpm - Standard",
    ("nsr", "mosler", "supporto motore"): "Anglewinder - Evo - Extra Hard (Rosso)",
    ("nsr", "mosler", "corona"): "Anglewinder Alluminio - 31 denti - 16.8mm",
    ("nsr", "mosler", "pignoni"): "Anglewinder - 13 denti - 7.5m",
    ("nsr", "mosler", "assale anteriore"): '3/32" - Standard - Acciaio Rettificato - 55mm',
    ("nsr", "mosler", "assale posteriore"): '3/32" - Standard - Acciaio Rettificato - 55mm',
    ("nsr", "mosler", "cerchi anteriori"): "Anteriori - Alluminio - No Air System - Standard - 16x8mm",
    ("nsr", "mosler", "cerchi posteriori"): "Posteriori - Alluminio - Air System - Standard - 16x8mm",
    ("nsr", "mosler", "pickup"): "Pickup Racing a Lama Lunga",
    ("nsr", "mosler", "dettaglio supporto"): "Standard - Autolubrificanti",
    ("nsr", "mosler", "gomme posteriori"): "NSR 5279Z 19.5x11",

    ("nsr", "altri modelli", "motore"): "King - Evo3 - 21.400 rpm - Standard",
    ("nsr", "altri modelli", "supporto motore"): "Anglewinder - Evo - Extra Hard (Rosso)",
    ("nsr", "altri modelli", "corona"): "Anglewinder Alluminio - 31 denti - 16.8mm",
    ("nsr", "altri modelli", "pignoni"): "Anglewinder - 13 denti - 7.5m",
    ("nsr", "altri modelli", "assale anteriore"): '3/32" - Standard - Acciaio Rettificato - 55mm',
    ("nsr", "altri modelli", "assale posteriore"): '3/32" - Standard - Acciaio Rettificato - 55mm',
    ("nsr", "altri modelli", "cerchi anteriori"): "Anteriori Grandi No Air System - da 17.25x8mm",
    ("nsr", "altri modelli", "cerchi posteriori"): "Posteriori Grandi Air System da 17.25x10mm",
    ("nsr", "altri modelli", "forcella"): "1234",
    ("nsr", "altri modelli", "pickup"): "Black - Rally A stelo - Stelo Lungo",
    ("nsr", "altri modelli", "dettaglio supporto"): "Standard - Autolubrificanti",
    ("nsr", "altri modelli", "gomme posteriori"): "NSR 5271WRE 19.5x11",

    ("nsr", "f1 86/89", "motore"): "King - Evo3 - 21.400 rpm - Standard",
    ("nsr", "f1 86/89", "supporto motore"): "Inline - Evo - Standard (Nero)",
    ("nsr", "f1 86/89", "corona"): "in Linea Evo Nera - 27 denti",
    ("nsr", "f1 86/89", "pignoni"): "in linea - NSR Formula 86/89 - 10 denti",
    ("nsr", "f1 86/89", "assale anteriore"): '3/32" - Standard - Acciaio Rettificato - 60mm',
    ("nsr", "f1 86/89", "assale posteriore"): '3/32" - Standard - Acciaio Rettificato - 55mm',
    ("nsr", "f1 86/89", "cerchi anteriori"): "Anteriori - Standard - No Air System - Formula - 13x8mm",
    ("nsr", "f1 86/89", "cerchi posteriori"): "Posteriori Air System per Formula NSR - 13x10",
    ("nsr", "f1 86/89", "pickup"): "Advanced - Racing - A vite - Lama Corta",
    ("nsr", "f1 86/89", "dettaglio supporto"): "Standard - Autolubrificanti",
    ("nsr", "f1 86/89", "gomme anteriori"): "NSR 5290 16x8",
    ("nsr", "f1 86/89", "gomme posteriori"): "NSR 5287Z 19.5x13",

    ("slot.it", "gt3", "motore"): "Slot.it MX16-m",
    ("slot.it", "gt3", "supporto motore"): "Slot.it CH65",
    ("slot.it", "gt3", "corona"): "Slot.it GS1831",
    ("slot.it", "gt3", "pignoni"): "Slot.it PS11",
    ("slot.it", "gt3", "assale anteriore"): "Tutti gli assali Slot.it",
    ("slot.it", "gt3", "assale posteriore"): "Tutti gli assali Slot.it",
    ("slot.it", "gt3", "cerchi anteriori"): "Slot.it W17308215P",
    ("slot.it", "gt3", "cerchi posteriori"): "Slot.it W17308215A",
    ("slot.it", "gt3", "gomme anteriori"): "Slot.it PT15",
    ("slot.it", "gt3", "gomme posteriori"): "Slot.it PT1323",

    ("slot.it", "hypercar lmp", "motore"): "Slot.it MN13CH",
    ("slot.it", "hypercar lmp", "supporto motore"): "Tutti i supporti anglewinder Slot.it",
    ("slot.it", "hypercar lmp", "corona"): "Tutti gli ingranaggi angolari GA16xx (plastica o ergal)",
    ("slot.it", "hypercar lmp", "pignoni"): "Slot.it PS10",
    ("slot.it", "hypercar lmp", "assale anteriore"): "Tutti gli assali Slot.it",
    ("slot.it", "hypercar lmp", "assale posteriore"): "Tutti gli assali Slot.it",
    ("slot.it", "hypercar lmp", "cerchi anteriori"): "Tutte le ruote Slot.it diam. >=16.5mm",
    ("slot.it", "hypercar lmp", "cerchi posteriori"): "Tutte le ruote Slot.it diam. >=16.5mm",
    ("slot.it", "hypercar lmp", "pickup"): "Slot.it CH26",
    ("slot.it", "hypercar lmp", "gomme anteriori"): "Slot.it PT15",
    ("slot.it", "hypercar lmp", "gomme posteriori"): "Slot.it PT1171F22",

    ("slot.it", "gruppo c", "motore"): "Slot.it MX16",
    ("slot.it", "gruppo c", "supporto motore"): "Slot.it CH110",
    ("slot.it", "gruppo c", "corona"): "Slot.it GI23-BZ",
    ("slot.it", "gruppo c", "pignoni"): "Slot.it PI09",
    ("slot.it", "gruppo c", "assale anteriore"): "Tutti gli assali Slot.it",
    ("slot.it", "gruppo c", "assale posteriore"): "Tutti gli assali Slot.it",
    ("slot.it", "gruppo c", "cerchi anteriori"): "Slot.it W15808215P",
    ("slot.it", "gruppo c", "cerchi posteriori"): "Slot.it W16508215A",
    ("slot.it", "gruppo c", "pickup"): "Slot.it CH06",
    ("slot.it", "gruppo c", "gomme anteriori"): "Slot.it PT15",
    ("slot.it", "gruppo c", "gomme posteriori"): "Slot.it PT1207F22",

    ("slot.it", "dtm", "motore"): "Slot.it MX15",
    ("slot.it", "dtm", "supporto motore"): "Slot.it CH110",
    ("slot.it", "dtm", "corona"): "Slot.it GI23-BZ",
    ("slot.it", "dtm", "pignoni"): "Slot.it PI09",
    ("slot.it", "dtm", "assale anteriore"): "Slot.it PA01-45",
    ("slot.it", "dtm", "assale posteriore"): "Slot.it PA01-45",
    ("slot.it", "dtm", "cerchi anteriori"): "Slot.it W15808215P",
    ("slot.it", "dtm", "cerchi posteriori"): "Slot.it W15810215A",
    ("slot.it", "dtm", "pickup"): "Slot.it CH06",
    ("slot.it", "dtm", "gomme anteriori"): "Slot.it PT15",
    ("slot.it", "dtm", "gomme posteriori"): "Slot.it PT1207F22",

    ("slot.it", "classic", "motore"): "Slot.it MX16-m",
    ("slot.it", "classic", "supporto motore"): "Slot.it CH67",
    ("slot.it", "classic", "corona"): "Slot.it GS1831-LPL",
    ("slot.it", "classic", "pignoni"): "Slot.it PS11",
    ("slot.it", "classic", "assale anteriore"): "Tutti gli assali Slot.it",
    ("slot.it", "classic", "assale posteriore"): "Tutti gli assali Slot.it",
    ("slot.it", "classic", "cerchi anteriori"): "Tutte le ruote Slot.it 14.3x8.2mm",
    ("slot.it", "classic", "cerchi posteriori"): "Tutte le ruote Slot.it 15.8x8.2mm",
    ("slot.it", "classic", "pickup"): "Slot.it CH06",
    ("slot.it", "classic", "viti carrozzeria"): "Viti Metriche Slot.it",
    ("slot.it", "classic", "gomme anteriori"): "Slot.it PT15",
    ("slot.it", "classic", "gomme posteriori"): "Slot.it PT1207F22",

    ("thunderslot", "classic", "motore"): "Motor Mach 21500 rpm at 12 volts 175g/m Doppio albero",
    ("thunderslot", "classic", "supporto motore"): "Grey Hard",
    ("thunderslot", "classic", "corona"): "SW Corona Thunderslot",
    ("thunderslot", "classic", "pignoni"): "11 denti (bianco)",
    ("thunderslot", "classic", "telaio"): "Hard Grey",
    ("thunderslot", "classic", "cerchi anteriori"): "RMR003AL",
    ("thunderslot", "classic", "cerchi posteriori"): "RMR003AL",
    ("thunderslot", "classic", "pickup"): "Tutti i Pick-up Thunderslot",
    ("thunderslot", "classic", "viti carrozzeria"): "SC2.5HEX",
    ("thunderslot", "classic", "sospensioni"): "SUSK005/M",
    ("thunderslot", "classic", "dettaglio supporto"): "Bronzine/Cuscinetti Thunderslot",
    ("thunderslot", "classic", "assale"): "3/32 Assale Thunderslot",
    ("thunderslot", "classic", "gomme anteriori"): "TYR003FR",
    ("thunderslot", "classic", "gomme posteriori"): "TYR004R",
  }

  if p == "nsr" and c in {"f1 2022", "f1 22", "f122"}:
    c = "f1 22"
  if p == "nsr" and c in {"altri modelli", "altri_modelli"}:
    c = "altri modelli"
  if p == "slot.it" and c == "gruppoc":
    c = "gruppo c"
  if p == "thunderslot" and c == "classic":
    c = "classic"

  return defaults.get((p, c, f))


def upload_image_to_supabase(uploaded_file):
    if uploaded_file is None or supabase is None:
        return None

    allowed_types = {"image/jpeg": ".jpg", "image/png": ".png"}
    max_bytes = 10 * 1024 * 1024
    content_type = (uploaded_file.type or "").lower()
    if content_type not in allowed_types:
        st.error("Formato immagine non supportato. Usa JPG o PNG.")
        return None

    file_bytes = uploaded_file.getvalue()
    if len(file_bytes) > max_bytes:
        st.error("L'immagine è troppo grande. Il limite è di 10 MB.")
        return None

    file_ext = allowed_types[content_type]
    file_name = f"car_{int(time.time())}_{os.urandom(8).hex()}{file_ext}"
    try:
        supabase.storage.from_("immagini-garage").upload(
            path=file_name,
            file=file_bytes,
            file_options={"content-type": content_type, "upsert": "false"},
        )
        return supabase.storage.from_("immagini-garage").get_public_url(file_name)
    except Exception as e:
        st.error(f"Errore durante il caricamento dell'immagine nel cloud: {e}")
        return None


def validate_image_url(url):
  if not url:
    return None
  url = str(url).strip()
  try:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
      return None
    return url
  except ValueError:
    return None


def generate_pdf(config_name, modello_nome, dettagli, foto_url=None, produttore_nome=""):
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
      safe_foto_url = validate_image_url(foto_url)
      if safe_foto_url:
        response_img = requests.get(
            safe_foto_url, timeout=10, allow_redirects=True,
            headers={"User-Agent": "SlotGarage/1.0"}
        )
        content_type = (response_img.headers.get("Content-Type") or "").lower()
        if response_img.status_code == 200 and content_type.startswith("image/") and len(response_img.content) <= 10 * 1024 * 1024:
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

  is_thunder = produttore_nome and produttore_nome.lower() == "thunderslot"
  col_w = 90 if is_thunder else 93
  col1_x = 98
  col2_x = 197 if is_thunder else 194

  pesi_motore_keywords = [
      "peso_carrozzeria",
      "peso_totale",
      "carreggiata_post.",
      "giri_motore",
      "motore",
      "supporto_motore",
      "corona",
      "pignoni",
  ]

  dettagli_filtrati = {}
  chiavi_da_rimuovere = [
      "distanziali_ant.", "distanziali_post.", "distanziali_anteriori", 
      "distanziali_posteriori", "distanziale_anteriore", "distanziale_posteriore"
  ]

  for k, v in dettagli.items():
    if k.lower() == "note" or k.lower() == "foto_personalizzata_url":
      continue
    if k.lower() in chiavi_da_rimuovere:
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

  def draw_tech_section(x, y, w, title, items_dict, label_width=34, label_gap=3):
    pdf.set_fill_color(*bg_dark)
    pdf.set_text_color(*text_light)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_xy(x, y)
    pdf.cell(w, 6, f"   {title}", ln=True, fill=True)

    item_y = y + 7.5
    value_x = x + 3 + label_width + label_gap
    value_w = w - (3 + label_width + label_gap + 3)

    for k, v in items_dict.items():
      if not v or str(v).lower() == "no" or str(v).lower() == "nessuna":
        continue
      pdf.set_text_color(*text_dark)
      pdf.set_font("Helvetica", "", 8.5)

      label_aliases = {
          "tipo_sospensione_posteriori": "Tipo Sosp. Post.",
          "tipo_sospensione_laterali": "Tipo Sosp. Lat.",
          "tipo_sospensione_anteriori": "Tipo Sosp. Ant.",
          "durezza_molla_posteriori": "Durezza Molla Post.",
          "durezza_molla_laterali": "Durezza Molla Lat.",
          "durezza_molla_anteriori": "Durezza Molla Ant.",
          "sospensioni_posteriori": "Sospensioni Post.",
          "sospensioni_laterali": "Sospensioni Lat.",
          "sospensioni_anteriori": "Sospensioni Ant.",
          "gomme anteriori": "Gomme Anteriori",
          "gomme posteriori": "Gomme Posteriori",
      }
      k_str = str(k).strip()
      k_norm = "_".join(k_str.lower().replace("-", " ").split())
      k_clean = label_aliases.get(k_norm, k_str.replace("_", " "))
      v_clean = str(v)

      pdf.set_xy(x + 3, item_y)
      pdf.cell(label_width, 4.8, f"{k_clean}:", 0, 0)

      pdf.set_font("Helvetica", "B", 8.5)
      pdf.set_xy(value_x, item_y)

      start_val_y = pdf.get_y()
      pdf.multi_cell(value_w, 4.2, f"{v_clean}")
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
      label_width=50 if is_thunder else 42,
      label_gap=4,
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


# ===== FUNZIONI DI NORMALIZZAZIONE =====
def _normalizza_testo_filtro(valore):
    if valore is None:
        return ""
    testo = str(valore).strip().casefold()
    testo = unicodedata.normalize("NFKD", testo)
    testo = "".join(ch for ch in testo if not unicodedata.combining(ch))
    testo = testo.replace("-", " ").replace("_", " ")
    return " ".join(testo.split())

def _forcella_nsr_abilitata():
    if str(selected_prod_name or "").strip().casefold() != "nsr":
        return False

    mod = str(selected_model_name or "").strip().casefold()

    modelli_senza_forcella = [
        "mclaren 720s",
        "corvette c8.r",
        "mercedes amg",
        "mercedes-amg",
    ]

    for senza in modelli_senza_forcella:
        if senza in mod:
            return False

    mod_compatto = re.sub(r"[^a-z0-9]+", "", mod)
    modelli_forcella = (
        "corvette c6.r",
        "corvette c7.r",
        "asv gt3",
        "audi r8 lms",
        "bmw z4",
        "porsche 997 gt3",
        "porsche 997",
    )
    return any(
        re.sub(r"[^a-z0-9]+", "", nome) in mod_compatto
        for nome in modelli_forcella
    )


# ============================================================
# FUNZIONI REGOLAMENTO
# ============================================================

def _norm_regola(valore):
    import unicodedata
    if valore is None:
        return ""
    testo = str(valore).strip().casefold()
    testo = unicodedata.normalize("NFKD", testo)
    testo = "".join(ch for ch in testo if not unicodedata.combining(ch))
    testo = testo.replace("–", "-").replace("—", "-").replace("_", " ")
    return " ".join(testo.split())

def _normalizza_codice_prodotto(valore):
    if valore is None:
        return ""
    testo = str(valore).strip().casefold()
    if testo.endswith(".0"):
        parte_numerica = testo[:-2]
        if parte_numerica.isdigit():
            testo = parte_numerica
    return "".join(testo.split())

def _descrizione_catalogo_per_regolamento(componente):
    if not componente:
        return ""

    prodotto = str(componente.get("Prodotto") or "").strip()
    materiale = str(componente.get("Materiale") or "").strip()
    misure = str(componente.get("Misure") or "").strip()
    tipo = str(componente.get("Tipo") or "").strip()

    parti = []
    if prodotto:
        parti.append(prodotto)
    if materiale and materiale.casefold() != "none":
        parti.append(materiale)
    if misure and misure.casefold() != "none":
        parti.append(misure)
    if tipo and tipo.casefold() != "none":
        parti.append(tipo)

    return " - ".join(parti)

def _indicizza_catalogo_per_codice():
    indice = {}
    for componente in catalogo_componenti or []:
        if not componente:
            continue
        codice = componente.get("Codice_Prodotto")
        if codice is None:
            codice = componente.get("codice_prodotto")
        codice_norm = _normalizza_codice_prodotto(codice)
        if not codice_norm:
            continue
        if codice_norm not in indice:
            indice[codice_norm] = componente
    return indice

def _risolvi_regola_con_catalogo(valore, indice_codici):
    valore_originale = "" if valore is None else str(valore).strip()
    codice_norm = _normalizza_codice_prodotto(valore_originale)
    if not codice_norm:
        return valore_originale

    componente = indice_codici.get(codice_norm)
    if not componente:
        return valore_originale

    codice_db = componente.get("Codice_Prodotto")
    if codice_db is None:
        codice_db = componente.get("codice_prodotto")
    codice_display = str(codice_db).strip() if codice_db is not None else valore_originale
    descrizione = _descrizione_catalogo_per_regolamento(componente)

    if descrizione:
        return f"{codice_display} - {descrizione}"
    return codice_display

def _carica_regole_semplici(prod_id, cat_id, sotto_categoria=None, categoria_nome=None):
    def _norm_reg_filtro(value):
        if value is None:
            return ""
        import unicodedata
        s = str(value).strip().casefold()
        s = unicodedata.normalize("NFKD", s)
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        s = s.replace("_", " ").replace("-", " ").replace("/", " ")
        return " ".join(s.split())

    def _match_reg_categoria(csv_value, ui_value):
        a = _norm_reg_filtro(csv_value)
        b = _norm_reg_filtro(ui_value)
        if not b or a == b:
            return True
        alias = {
            "gruppo c": {"gruppo c", "gruppoc", "group c"},
            "hypercar": {"hypercar", "hypercar lmp", "lmp"},
            "gt3": {"gt3", "gt 3"},
            "dtm": {"dtm", "dtm 2020", "dtm2020"},
            "classic": {"classic", "classiche"},
        }
        return any(
            (b == canon and a in vals) or (a == canon and b in vals)
            for canon, vals in alias.items()
        )

    def _match_reg_livello(csv_value, ui_value):
        a = _norm_reg_filtro(csv_value)
        b = _norm_reg_filtro(ui_value)
        if not b or a == b:
            return True
        alias = {
            "box stock": {"box stock", "boxstock", "standard", "stock"},
            "evo": {"evo", "evolution"},
            "evo f": {"evo f", "evo/f", "evo-f", "evof"},
            "evo2": {"evo2", "evo 2", "evolution 2"},
            "p1": {"p1", "p 1"},
            "p2": {"p2", "p 2"},
            "prototipi": {"prototipi", "prototypes"},
            "sport": {"sport"},
        }
        return any(
            (b == canon and a in vals) or (a == canon and b in vals)
            for canon, vals in alias.items()
        )

    try:
        csv_path = os.path.join(os.path.dirname(__file__), "regolamento.csv")
        
        if not os.path.exists(csv_path):
            st.warning(f"⚠️ File regolamento.csv non trovato in {csv_path}.")
            return {}
        
        regole_per_campo = {}
        mappa_campi = {
            "motore": "Motore",
            "supporto motore": "Supporto Motore",
            "corona": "Corona",
            "pignoni": "Pignoni",
            "pignone": "Pignoni",
            "assale anteriore": "Assale Anteriore",
            "assale posteriore": "Assale Posteriore",
            "cerchi anteriori": "Cerchi Anteriori",
            "cerchi posteriori": "Cerchi Posteriori",
            "pickup": "Pickup",
            "forcella": "Forcella",
            "gomme anteriori": "Gomme Anteriori",
            "gomme posteriori": "Gomme Posteriori",
            "viti carrozzeria": "Viti Carrozzeria",
            "viti metriche sospensioni": "Viti Metriche Sospensioni",
            "sospensioni": "Sospensioni",
            "dettaglio supporto": "Dettaglio_Supporto",
            "tipo sospensione": "Tipo_Sospensione",
            "stopper": "Stopper",
        }
        
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if str(row.get("id_produttori")).strip() != str(prod_id).strip():
                    continue
                if str(selected_prod_name if "selected_prod_name" in locals() else "").strip().casefold() != "slot.it":
                    if str(row.get("id_categorie")).strip() != str(cat_id).strip():
                        continue
                if (
                    sotto_categoria is not None
                    and not _match_reg_livello(row.get("sotto_categoria", ""), sotto_categoria)
                ):
                    continue
                if (
                    categoria_nome is not None
                    and not _match_reg_categoria(row.get("categoria_nome", ""), categoria_nome)
                ):
                    continue
                
                campo = row.get("campo")
                valore = row.get("valoreregola")
                if campo and valore:
                    campo_norm = campo.lower().strip()
                    campo_originale = mappa_campi.get(campo_norm, campo)
                    if campo_originale not in regole_per_campo:
                        regole_per_campo[campo_originale] = []
                    indice_codici = _indicizza_catalogo_per_codice()
                    valore_mostrato = _risolvi_regola_con_catalogo(valore, indice_codici)
                    if valore_mostrato not in regole_per_campo[campo_originale]:
                        regole_per_campo[campo_originale].append(valore_mostrato)
        
        if regole_per_campo:
            st.session_state.regolamento_dati = regole_per_campo
            st.session_state.regolamento_attivo = True
            st.success(f"✅ Caricate {sum(len(v) for v in regole_per_campo.values())} regole da CSV")
        else:
            st.warning(f"⚠️ Nessuna regola trovata per produttore {prod_id}, categoria {cat_id}")
        
        return regole_per_campo
    except Exception as e:
        st.error(f"❌ Errore durante il caricamento del CSV: {e}")
        return {}

# ============================================================
# FUNZIONE PER CONTROLLARE ARCHIVIO COMPONENTI (PUNTO 6)
# ============================================================
def componente_in_archivio(nome_componente):
    if not st.session_state.user:
        return False
    try:
        result = supabase.table("SlotGarage_Componenti").select("id")\
            .eq("user_id", st.session_state.user.id)\
            .ilike("nome", f"%{nome_componente}%")\
            .execute()
        return len(result.data or []) > 0
    except Exception:
        return False


# ============================================================
# GESTIONE SEZIONI (TAB)
# ============================================================

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

      model_safe_key = re.sub(r"[^a-zA-Z0-9_]+", "_", str(selected_model_name)).strip("_") or "modello"

      _reg_target = (str(prod_id_selezionato), str(category_id), str(selected_model_name))
      if st.session_state.get("configura_regolamento_target") not in (None, _reg_target):
        st.session_state.configura_regolamento_target = None

      _reg_attivo = st.session_state.get("configura_regolamento_target") == _reg_target
      
      if selected_prod_name.lower() != "slot.it":
          col_reg1, col_reg2 = st.columns([1, 1])
          with col_reg1:
              if not _reg_attivo:
                  if st.button("📖 Configura da Regolamento", key=f"config_reg_{model_safe_key}"):
                      st.session_state.configura_regolamento_target = _reg_target
                      sotto_cat = None
                      cat_nome = None
                      _carica_regole_semplici(
                          prod_id_selezionato, category_id, sotto_cat, cat_nome
                      )
                      st.rerun()
              else:
                  st.success("✅ Configurazione da Regolamento attiva")
          with col_reg2:
              if _reg_attivo:
                  if st.button("↩️ Torna a Box Stock", key=f"boxstock_reg_{model_safe_key}"):
                      st.session_state.configura_regolamento_target = None
                      st.session_state.regolamento_attivo = False
                      st.session_state.regolamento_dati = {}
                      st.rerun()

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

        if selected_prod_name.lower() == "slot.it" and selected_cat_name != "Tutte":
            _slotit_cat_map = {
                "hypercar": "Hypercar",
                "gruppo c": "Gruppo C",
                "gruppoc": "Gruppo C",
                "gt3": "GT3",
                "dtm": "DTM",
                "classic": "Classic",
            }
            import unicodedata
            _cat_norm = str(selected_cat_name).strip().casefold()
            _cat_norm = unicodedata.normalize("NFKD", _cat_norm)
            _cat_norm = "".join(
                ch for ch in _cat_norm if not unicodedata.combining(ch)
            )
            _cat_norm = " ".join(_cat_norm.replace("_", " ").replace("-", " ").split())
            _slotit_cat_direct = _slotit_cat_map.get(_cat_norm)
            if _slotit_cat_direct:
                st.session_state[f"slotit_categoria_{model_safe_key}"] = _slotit_cat_direct


        pezzi = []
        pezzi_produttore = []
        for p in catalogo_componenti:
          if not p or p.get("id_Produttori") != prod_id_selezionato:
            continue

          pezzi_produttore.append(p)

          cat_componente = (
              p.get("category_id")
              if p.get("category_id") is not None
              else (
                  p.get("id_Categorie")
                  if p.get("id_Categorie") is not None
                  else p.get("categoria")
              )
          )
          if cat_componente is None or str(cat_componente) == str(category_id):
            pezzi.append(p)

        scelte_utente = {}

        MATERIALE_PER_PRODUTTORE_CATEGORIA = {
          1: {
            "gt3": "anglewinder",
            "hypercar": "sidewinder",
            "classic": "sidewinder",
            "f1 86/89": "in linea",
            "f1 2022": "in linea",
            "f1 22": "in linea",
            "f122": "in linea",
            "mosler": "anglewinder",
            "altri modelli": "anglewinder",
            "altri_modelli": "anglewinder",
          },
          2: {
            "hypercar": "anglewinder",
            "hypercar lmp": "anglewinder",
            "classic": "sidewinder",
            "gt3": "sidewinder",
            "dtm": "in linea",
            "gruppo c": "in linea",
            "gruppoc": "in linea",
          },
        }

        def materiale_richiesto_per_categoria():
          if not prod_id_selezionato or not category_id:
            return None

          prod_id = int(prod_id_selezionato) if str(prod_id_selezionato).isdigit() else prod_id_selezionato
          regole_produttore = MATERIALE_PER_PRODUTTORE_CATEGORIA.get(prod_id)
          if not regole_produttore:
            return None

          categoria_norm = _normalizza_testo_filtro(selected_cat_name)

          materiale = regole_produttore.get(categoria_norm)
          if materiale:
            return materiale

          if categoria_norm.startswith("f1 86"):
            return regole_produttore.get("f1 86/89")
          if categoria_norm in {"f1 2022", "f1 22", "f122"}:
            return regole_produttore.get("f1 2022") or regole_produttore.get("f122")
          if categoria_norm in {"gruppo c", "gruppoc"}:
            return regole_produttore.get("gruppo c") or regole_produttore.get("gruppoc")

          return None

        def filtra_per_materiale_configurazione(campo, lista_pezzi):
          campo_norm = _normalizza_testo_filtro(campo)

          if (
              str(prod_id_selezionato) == "2"
              and _normalizza_testo_filtro(selected_cat_name) == "hypercar lmp"
              and campo_norm in {"pignoni", "pignone"}
          ):
            return lista_pezzi

          campi_con_filtro_materiale = {
            "supporto motore",
            "pignoni",
            "pignone",
            "corona",
          }

          if campo_norm not in campi_con_filtro_materiale:
            return lista_pezzi

          materiale_richiesto = materiale_richiesto_per_categoria()
          if not materiale_richiesto:
            return lista_pezzi

          target = _normalizza_testo_filtro(materiale_richiesto)
          filtrati = []

          for p in lista_pezzi:
            materiale = _normalizza_testo_filtro(p.get("Materiale"))
            if not materiale:
              continue

            if target in materiale:
              filtrati.append(p)

          return filtrati

        def helper_filtra_pezzi_thunderslot(campo, pezzi):
            c_low = _normalizza_testo_filtro(campo)
            if not pezzi:
                return []
            if "motore" in c_low and "supporto" not in c_low:
                return [p for p in pezzi if p and p.get("Prodotto") 
                        and "motore" in _normalizza_testo_filtro(p.get("Prodotto"))
                        and "supporto" not in _normalizza_testo_filtro(p.get("Prodotto"))]
            if "supporto" in c_low and "motore" in c_low:
                return [p for p in pezzi if p and p.get("Prodotto") 
                        and "supporto" in _normalizza_testo_filtro(p.get("Prodotto"))]
            if "corona" in c_low:
                return [p for p in pezzi if p and p.get("Prodotto") 
                        and "corona" in _normalizza_testo_filtro(p.get("Prodotto"))]
            if "pignon" in c_low or "pignone" in c_low:
                return [p for p in pezzi if p and p.get("Prodotto") 
                        and ("pignon" in _normalizza_testo_filtro(p.get("Prodotto"))
                        or "pignone" in _normalizza_testo_filtro(p.get("Prodotto")))]
            if "telaio" in c_low:
                return [p for p in pezzi if p and p.get("Prodotto") 
                        and "telaio" in _normalizza_testo_filtro(p.get("Prodotto"))]
            if "assale" in c_low:
                return [p for p in pezzi if p and p.get("Prodotto") 
                        and "assale" in _normalizza_testo_filtro(p.get("Prodotto"))]
            if "cerch" in c_low:
                return [p for p in pezzi if p and p.get("Prodotto") 
                        and "cerch" in _normalizza_testo_filtro(p.get("Prodotto"))]
            if "pickup" in c_low:
                return [p for p in pezzi if p and p.get("Prodotto") 
                        and ("pickup" in _normalizza_testo_filtro(p.get("Prodotto"))
                        or "pick up" in _normalizza_testo_filtro(p.get("Prodotto")))]
            if "viti carrozzeria" in c_low or "viti" in c_low:
                return [p for p in pezzi if p and p.get("Prodotto") 
                        and ("viti" in _normalizza_testo_filtro(p.get("Prodotto"))
                        or "vite" in _normalizza_testo_filtro(p.get("Prodotto"))
                        or "carrozz" in _normalizza_testo_filtro(p.get("Prodotto")))]
            return pezzi

        def helper_filtra_pezzi(campo, pezzi):
          c = _normalizza_testo_filtro(campo)
          if not pezzi:
              return []

          if c == "supporto motore":
            lista = [
                p for p in pezzi
                if p and p.get("Prodotto")
                and "supporto" in _normalizza_testo_filtro(p.get("Prodotto"))
                and "motore" in _normalizza_testo_filtro(p.get("Prodotto"))
            ]
            return filtra_per_materiale_configurazione("supporto motore", lista)

          if c == "motore":
            return [
                p for p in pezzi
                if p and p.get("Prodotto")
                and _normalizza_testo_filtro(p.get("Prodotto")) == "motore"
            ]

          if c == "corona":
            lista = [
                p for p in pezzi
                if p and p.get("Prodotto")
                and "corona" in _normalizza_testo_filtro(p.get("Prodotto"))
            ]
            return filtra_per_materiale_configurazione("corona", lista)

          if c in {"pignoni", "pignone"}:
            lista = [
                p for p in pezzi
                if p and p.get("Prodotto")
                and (
                    "pignon" in _normalizza_testo_filtro(p.get("Prodotto"))
                    or "pignone" in _normalizza_testo_filtro(p.get("Prodotto"))
                )
            ]
            return filtra_per_materiale_configurazione("pignoni", lista)

          if c == "telaio":
            lista = [
              p for p in pezzi
              if p and p.get("Prodotto")
              and "telaio" in _normalizza_testo_filtro(p.get("Prodotto"))
            ]

            if not lista:
              return []

            modello = _normalizza_testo_filtro(selected_model_name)

            if not modello or modello == "tutti":
              return lista

            def testo_telaio(p):
              materiale = str(p.get("Materiale") or "")
              misure = str(p.get("Misure") or "")
              return _normalizza_testo_filtro(f"{materiale} {misure}")

            trovati = [
              p for p in lista
              if modello in testo_telaio(p)
            ]
            if trovati:
              if str(selected_prod_name or "").strip().casefold() == "nsr":
                def _telaio_nero_trovato(p):
                  testo = _normalizza_testo_filtro(
                      f"{p.get('Materiale') or ''} {p.get('Misure') or ''}"
                  )
                  return "standard nero" in testo or "nero" in testo
                trovati = [p for p in trovati if _telaio_nero_trovato(p)] + [
                    p for p in trovati if not _telaio_nero_trovato(p)
                ]
              return trovati

            parole = [w for w in modello.split() if len(w) > 2]
            if parole:
              trovati = [
                p for p in lista
                if any(w in testo_telaio(p) for w in parole)
              ]
              if trovati:
                if str(selected_prod_name or "").strip().casefold() == "nsr":
                  def _telaio_nero_parole(p):
                    testo = _normalizza_testo_filtro(
                        f"{p.get('Materiale') or ''} {p.get('Misure') or ''}"
                    )
                    return "standard nero" in testo or "nero" in testo
                  trovati = [p for p in trovati if _telaio_nero_parole(p)] + [
                      p for p in trovati if not _telaio_nero_parole(p)
                  ]
                return trovati

            risultato = lista

            if str(selected_prod_name or "").strip().casefold() == "nsr":
              def _telaio_nero(p):
                testo = _normalizza_testo_filtro(
                    f"{p.get('Materiale') or ''} {p.get('Misure') or ''}"
                )
                return "standard nero" in testo or "nero" in testo

              neri = [p for p in risultato if _telaio_nero(p)]
              altri = [p for p in risultato if not _telaio_nero(p)]
              risultato = neri + altri

            return risultato

          if c == "forcella":
            risultato_forcelle = [
                p for p in pezzi
                if p and p.get("Prodotto")
                and "forcell" in _normalizza_testo_filtro(p.get("Prodotto"))
            ]

            if not risultato_forcelle:
              risultato_forcelle = [
                  p for p in pezzi_produttore
                  if p and p.get("Prodotto")
                  and "forcell" in _normalizza_testo_filtro(p.get("Prodotto"))
              ]

            return risultato_forcelle

          if c in {"assale anteriore", "assale posteriore"}:
            risultato_assali = [
                p for p in pezzi
                if p and p.get("Prodotto")
                and "assale" in _normalizza_testo_filtro(p.get("Prodotto"))
            ]

            if not risultato_assali:
              risultato_assali = [
                  p for p in pezzi_produttore
                  if p and p.get("Prodotto")
                  and "assale" in _normalizza_testo_filtro(p.get("Prodotto"))
              ]

            return risultato_assali

          if c in {"cerchi anteriori", "cerchi posteriori"}:
            risultato = []
            for p in pezzi:
              if not p or not p.get("Prodotto"):
                continue
              testo_cerchio = " ".join(
                  str(p.get(k) or "")
                  for k in ("Prodotto", "Materiale", "Misure")
              )
              testo_cerchio = _normalizza_testo_filtro(testo_cerchio)

              if "cerch" not in testo_cerchio:
                continue

              if c == "cerchi anteriori":
                if "posteriore" in testo_cerchio or "posteriori" in testo_cerchio:
                  continue
              else:
                if "anteriore" in testo_cerchio or "anteriori" in testo_cerchio:
                  continue

              risultato.append(p)
            return risultato

          if c == "pickup":
            risultato = []
            for p in pezzi:
              if not p or not p.get("Prodotto"):
                continue
              testo_pickup = " ".join(
                  str(p.get(k) or "")
                  for k in ("Prodotto", "Materiale", "Misure")
              )
              testo_pickup = _normalizza_testo_filtro(testo_pickup)

              if "pickup" not in testo_pickup and "pick up" not in testo_pickup:
                continue

              if "distanzial" in testo_pickup or "spacer" in testo_pickup:
                continue

              risultato.append(p)
            return risultato

          if c == "viti carrozzeria":
            return [
                p for p in pezzi
                if p and p.get("Prodotto")
                and "vit" in _normalizza_testo_filtro(p.get("Prodotto"))
                and "carrozz" in _normalizza_testo_filtro(p.get("Prodotto"))
            ]

          if c in {"gomme anteriori", "gomme anteriore"}:
              risultato = []
              for p in pezzi:
                  if not p or not p.get("Prodotto"):
                      continue

                  prodotto = _normalizza_testo_filtro(p.get("Prodotto"))
                  materiale = _normalizza_testo_filtro(p.get("Materiale"))
                  misure = _normalizza_testo_filtro(p.get("Misure"))
                  testo_gomma = " ".join(
                      x for x in (prodotto, materiale, misure) if x
                  )

                  if "gomm" not in prodotto and "gomm" not in testo_gomma:
                      continue

                  if "posterior" in materiale or "posterior" in misure:
                      continue

                  if (
                      "anterior" in materiale
                      or "anterior" in misure
                  ):
                      risultato.append(p)

              return risultato

          if c in {"gomme posteriori", "gomme posteriore"}:
              risultato = []
              for p in pezzi:
                  if not p or not p.get("Prodotto"):
                      continue

                  prodotto = _normalizza_testo_filtro(p.get("Prodotto"))
                  materiale = _normalizza_testo_filtro(p.get("Materiale"))
                  misure = _normalizza_testo_filtro(p.get("Misure"))
                  testo_gomma = " ".join(
                      x for x in (prodotto, materiale, misure) if x
                  )

                  if "gomm" not in prodotto and "gomm" not in testo_gomma:
                      continue

                  if "anterior" in materiale or "anterior" in misure:
                      continue

                  if (
                      "posterior" in materiale
                      or "posterior" in misure
                  ):
                      risultato.append(p)

              return risultato

          return []

        def _testo_catalogo_regola(p):
          return " ".join(
              str(p.get(k) or "")
              for k in ("Prodotto", "Materiale", "Misure", "Tipo")
          )

        # ============================================================
        # FUNZIONE RENDER_SELECT_COMPONENTE MODIFICATA (con badge archivio)
        # ============================================================
        def render_select_componente(campo, sub_pezzi_list, key_prefix):
            if st.session_state.regolamento_attivo:
                reg_campo = campo
                if campo in ["Assale Anteriore", "Assale Posteriore"] and campo not in st.session_state.regolamento_dati and "Assale" in st.session_state.regolamento_dati:
                    reg_campo = "Assale"
                if reg_campo in st.session_state.regolamento_dati:
                    opzioni = st.session_state.regolamento_dati[reg_campo]
                    saved_val = edit_data.get(campo) if edit_data else None
                    idx = 0
                    if saved_val and saved_val in opzioni:
                        idx = opzioni.index(saved_val)
                    return st.selectbox(
                        campo,
                        opzioni,
                        index=idx,
                        key=f"reg_{campo}_{model_safe_key}",
                    )
            
            opzioni = []
            match_values = []
            boxstock_val = _boxstock_target(selected_prod_name, selected_cat_name, campo)

            for p in sub_pezzi_list:
                prodotto = str(p.get("Prodotto") or "").strip()
                mat = p.get("Materiale")
                mis = p.get("Misure")
                parte_mat = str(mat).strip() if mat and str(mat).lower() != "none" else ""
                parte_mis = str(mis).strip() if mis and str(mis).lower() != "none" else ""

                if parte_mat and parte_mis:
                    str_opt = f"{parte_mat} - {parte_mis}"
                elif parte_mat or parte_mis:
                    str_opt = parte_mat or parte_mis
                else:
                    str_opt = prodotto

                if str_opt and str_opt not in opzioni:
                    # ---- PUNTO 6: CONTROLLO ARCHIVIO ----
                    in_archivio = componente_in_archivio(str_opt)
                    if in_archivio:
                        str_opt_display = f"{str_opt} ✅"
                    else:
                        str_opt_display = str_opt
                    opzioni.append(str_opt_display)
                    match_values.append((str_opt_display, prodotto, parte_mat, parte_mis))

            if not opzioni and boxstock_val:
                saved_val = edit_data.get(campo) if edit_data else None
                default_val = saved_val if saved_val else boxstock_val
                in_archivio = componente_in_archivio(default_val)
                display_val = f"{default_val} ✅" if in_archivio else default_val
                return st.selectbox(
                    campo,
                    [display_val],
                    index=0,
                    key=f"{key_prefix}_{campo}_{model_safe_key}",
                )
            
            saved_val = edit_data.get(campo) if edit_data else None
            target_for_default = saved_val if saved_val else boxstock_val
            
            def_idx = 0
            if target_for_default:
                for i, opt in enumerate(opzioni):
                    if target_for_default in opt:
                        def_idx = i
                        break
            elif boxstock_val:
                for i, opt in enumerate(opzioni):
                    if boxstock_val in opt:
                        def_idx = i
                        break

            if not opzioni:
                opzioni = ["Nessuna opzione"]
                def_idx = 0

            return st.selectbox(
                campo,
                opzioni,
                index=def_idx,
                key=f"{key_prefix}_{campo}_{model_safe_key}",
            )

        # --------------------------------------------
        # CONFIGURAZIONE PER I DIVERSI PRODUTTORI
        # --------------------------------------------

        if _reg_attivo:
          if selected_prod_name.lower() == "slot.it":
              st.caption("Confronto configurazione: Box Stock vs Regolamento")
          
          confronto_campi = [
              "Motore", "Supporto Motore", "Corona", "Pignoni",
              "Assale Anteriore", "Assale Posteriore",
              "Cerchi Anteriori", "Cerchi Posteriori", "Pickup", "Forcella",
              "Gomme Anteriori", "Gomme Posteriori"
          ]
          righe_confronto = []
          for _campo_confronto in confronto_campi:
            _categoria_boxstock = selected_cat_name
            if selected_prod_name.lower() == "slot.it":
                _categoria_boxstock = st.session_state.get(
                    f"slotit_categoria_{model_safe_key}",
                    selected_cat_name,
                )
                if str(_categoria_boxstock).strip().casefold() == "hypercar":
                    _categoria_boxstock = "hypercar lmp"

            _stock = _boxstock_target(
                selected_prod_name, _categoria_boxstock, _campo_confronto
            )
            reg_text = "Nessuna regola"
            if _campo_confronto in st.session_state.regolamento_dati:
                reg_text = " / ".join(st.session_state.regolamento_dati[_campo_confronto])
            righe_confronto.append({
                "Componente": _campo_confronto,
                "Box Stock": _stock or "—",
                "Regolamento": reg_text,
            })
          if righe_confronto:
            st.dataframe(
                righe_confronto,
                use_container_width=True,
                hide_index=True,
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
            scelte_utente["Carreggiata_Posteriore"] = st.text_input(
                "Carreggiata Posteriore",
                value=str(edit_data.get("Carreggiata_Posteriore", edit_data.get("Misura_Assale_Posteriore", ""))) if edit_data else "",
                key=f"carreggiata_posteriore_{model_safe_key}"
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
            scelte_utente["Distanziale_alla_corona"] = st.text_input(
                "Distanziale alla corona",
                value=str(edit_data.get("Distanziale_alla_corona", "")) if edit_data else "",
                key=f"altri_dist_corona_{model_safe_key}"
            )
          with col_d2:
            scelte_utente["Distanziale_alla_ruota"] = st.text_input(
                "Distanziale alla ruota",
                value=str(edit_data.get("Distanziale_alla_ruota", "")) if edit_data else "",
                key=f"altri_dist_ruota_{model_safe_key}"
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

          st.write("### 🏁 Gomme")
          col_gomme1, col_gomme2 = st.columns(2)
          with col_gomme1:
              scelte_utente["Gomme Anteriori"] = st.text_input(
                  "Gomme Anteriori",
                  value=str(edit_data.get("Gomme Anteriori", "")) if edit_data else "",
                  key=f"gomme_ant_altri_{model_safe_key}"
              )
          with col_gomme2:
              scelte_utente["Gomme Posteriori"] = st.text_input(
                  "Gomme Posteriori",
                  value=str(edit_data.get("Gomme Posteriori", "")) if edit_data else "",
                  key=f"gomme_post_altri_{model_safe_key}"
              )

        elif selected_prod_name.lower() == "slot.it":
          col1_slot, col2_slot = st.columns(2)

          slot_categorie = [
              "Hypercar",
              "Gruppo C",
              "GT3",
              "DTM",
              "Classic"
          ]

          slot_sottocategorie = {
              "Hypercar": ["P1", "P2"],
              "Gruppo C": ["Box Stock", "Evo", "Evo/F"],
              "GT3": ["Box Stock", "Evo", "Evo2"],
              "DTM": ["Box Stock", "Evo", "Evo2"],
              "Classic": ["Prototipi", "Sport"]
          }

          def_cat = edit_data.get("Categoria_SlotIt", "Hypercar") if edit_data else "Hypercar"
          def_sub = edit_data.get("SottoCategoria_SlotIt", "P1") if edit_data else "P1"

          cat_key = f"slotit_categoria_{model_safe_key}"
          sub_key = f"slotit_sottocategoria_{model_safe_key}"
          prev_cat_key = f"{cat_key}__prev"

          with col1_slot:
              if cat_key not in st.session_state:
                  st.session_state[cat_key] = (
                      def_cat if def_cat in slot_categorie else slot_categorie[0]
                  )

              categoria_slotit = st.selectbox(
                  "Categoria",
                  slot_categorie,
                  key=cat_key,
              )
              scelte_utente["Categoria_SlotIt"] = categoria_slotit

          sottocategorie_disponibili = slot_sottocategorie.get(
              categoria_slotit, []
          )

          categoria_precedente = st.session_state.get(prev_cat_key)

          if categoria_precedente is None:
              st.session_state[sub_key] = (
                  def_sub if def_sub in sottocategorie_disponibili
                  else (
                      sottocategorie_disponibili[0]
                      if sottocategorie_disponibili else ""
                  )
              )
          elif categoria_precedente != categoria_slotit:
              st.session_state[sub_key] = (
                  sottocategorie_disponibili[0]
                  if sottocategorie_disponibili else ""
              )
          elif st.session_state.get(sub_key) not in sottocategorie_disponibili:
              st.session_state[sub_key] = (
                  sottocategorie_disponibili[0]
                  if sottocategorie_disponibili else ""
              )

          st.session_state[prev_cat_key] = categoria_slotit

          with col2_slot:
              if sottocategorie_disponibili:
                  scelte_utente["SottoCategoria_SlotIt"] = st.selectbox(
                      "Livello",
                      sottocategorie_disponibili,
                      key=sub_key,
                  )
              else:
                  scelte_utente["SottoCategoria_SlotIt"] = ""

          # ---- PUNTO 1: BOTTONI (CONFIGURA, AGGIORNA, TORNA, SETUP SUGGERITO) ----
          col_reg_slot1, col_reg_slot2, col_reg_slot3, col_reg_slot4 = st.columns(4)

          with col_reg_slot1:
              if not _reg_attivo:
                  if st.button(
                      "📖 Configura da Regolamento",
                      key=f"config_reg_{model_safe_key}"
                  ):
                      st.session_state.configura_regolamento_target = _reg_target
                      sotto_cat = st.session_state.get(sub_key, "")
                      cat_nome = st.session_state.get(cat_key, "")
                      _carica_regole_semplici(
                          prod_id_selezionato,
                          category_id,
                          sotto_cat,
                          cat_nome
                      )
                      st.rerun()
              else:
                  st.success("✅ Regolamento attivo")

          with col_reg_slot2:
              if _reg_attivo:
                  if st.button(
                      "🔄 Aggiorna",
                      key=f"aggiorna_reg_{model_safe_key}"
                  ):
                      sotto_cat = st.session_state.get(sub_key, "")
                      cat_nome = st.session_state.get(cat_key, "")
                      _carica_regole_semplici(
                          prod_id_selezionato,
                          category_id,
                          sotto_cat,
                          cat_nome
                      )
                      st.rerun()

          with col_reg_slot3:
              if _reg_attivo:
                  if st.button(
                      "↩️ Torna a Box Stock",
                      key=f"boxstock_reg_{model_safe_key}"
                  ):
                      st.session_state.configura_regolamento_target = None
                      st.session_state.regolamento_attivo = False
                      st.session_state.regolamento_dati = {}
                      st.rerun()

          with col_reg_slot4:
              if _reg_attivo:
                  if st.button(
                      "🎯 Applica Setup Consigliato",
                      key=f"setup_suggerito_{model_safe_key}"
                  ):
                      for campo, valori in st.session_state.regolamento_dati.items():
                          if valori:
                              key_select = f"reg_{campo}_{model_safe_key}"
                              if key_select in st.session_state:
                                  st.session_state[key_select] = valori[0]
                      st.success("✅ Setup consigliato applicato! I dropdown sono stati impostati sul primo valore disponibile.")
                      st.rerun()

          col_peso1, col_peso2 = st.columns(2)
          with col_peso1:
              scelte_utente["Peso_Carrozzeria"] = st.text_input(
                  "Peso Carrozzeria",
                  value=str(edit_data.get("Peso_Carrozzeria", "")) if edit_data else "",
                  key=f"peso_carrozzeria_{model_safe_key}",
              )
          with col_peso2:
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
                  scelte_utente["Carreggiata_Posteriore"] = st.text_input(
                      "Carreggiata Posteriore",
                      value=str(edit_data.get("Carreggiata_Posteriore", edit_data.get("Misura_Assale_Posteriore", ""))) if edit_data else "",
                      key=f"carreggiata_posteriore_{model_safe_key}"
                  )
              else:
                sub_pezzi = helper_filtra_pezzi(campo, pezzi)
                scelte_utente[campo] = render_select_componente(campo, sub_pezzi, "slotit")

          st.write("### 🔩 Sospensioni")
          col_viti, col_tipo_sosp = st.columns(2)

          with col_viti:
            sub_viti_sosp = [
                p for p in pezzi
                if p and p.get("Prodotto") and p.get("Prodotto").strip().lower() == "viti metriche sospensioni"
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

          st.write("### 🏁 Gomme")
          col_gomme1, col_gomme2 = st.columns(2)
          with col_gomme1:
              sub_pezzi_gomme_ant = helper_filtra_pezzi("gomme anteriori", pezzi)
              scelte_utente["Gomme Anteriori"] = render_select_componente("Gomme Anteriori", sub_pezzi_gomme_ant, "gomme_ant_slotit")
          with col_gomme2:
              sub_pezzi_gomme_post = helper_filtra_pezzi("gomme posteriori", pezzi)
              scelte_utente["Gomme Posteriori"] = render_select_componente("Gomme Posteriori", sub_pezzi_gomme_post, "gomme_post_slotit")

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
            scelte_utente["Carreggiata_Posteriore"] = st.text_input(
                "Carreggiata Posteriore",
                value=str(edit_data.get("Carreggiata_Posteriore", edit_data.get("Misura_Assale_Posteriore", ""))) if edit_data else "",
                key=f"carreggiata_posteriore_{model_safe_key}"
            )

          if selected_prod_name.lower() == "nsr":
            nsr_campi = [
                "Motore",
                "Supporto Motore",
                "Corona",
                "Giri Motore",
                *(["Forcella"] if _forcella_nsr_abilitata() else []),
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
                  sub_pezzi = helper_filtra_pezzi(campo, pezzi)
                  scelte_utente[campo] = render_select_componente(campo, sub_pezzi, "nsr")

            st.write("### 🔩 Sospensioni")
            sosp_nsr_opts = ["No", "Sì"]
            def_sosp_nsr = edit_data.get("Sospensioni", "No") if edit_data else "No"
            idx_sosp_nsr = sosp_nsr_opts.index(def_sosp_nsr) if def_sosp_nsr in sosp_nsr_opts else 0
            sosp_nsr_attive = st.selectbox(
                "Sospensioni", sosp_nsr_opts, index=idx_sosp_nsr, key=f"nsr_sosp_sino_{model_safe_key}"
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

            st.write("### 🏁 Gomme")
            col_gomme1, col_gomme2 = st.columns(2)
            with col_gomme1:
                sub_pezzi_gomme_ant = helper_filtra_pezzi("gomme anteriori", pezzi)
                scelte_utente["Gomme Anteriori"] = render_select_componente("Gomme Anteriori", sub_pezzi_gomme_ant, "gomme_ant_nsr")
            with col_gomme2:
                sub_pezzi_gomme_post = helper_filtra_pezzi("gomme posteriori", pezzi)
                scelte_utente["Gomme Posteriori"] = render_select_componente("Gomme Posteriori", sub_pezzi_gomme_post, "gomme_post_nsr")

          elif selected_prod_name.lower() == "thunderslot":
            thunder_components = [
                p for p in catalogo_componenti
                if p and p.get("id_Produttori") == prod_id_selezionato
            ]
            
            if not thunder_components:
                st.warning("Nessun componente Thunderslot trovato nel catalogo.")
            
            thunder_campi = [
                "Motore",
                "Supporto Motore",
                "Corona",
                "Giri Motore",
                "Pignoni",
                "Telaio",
                "Cerchi Anteriori",
                "Cerchi Posteriori",
                "Viti Carrozzeria",
                "Assale Anteriore",
                "Assale Posteriore",
            ]

            cols = st.columns(3)
            for idx, campo in enumerate(thunder_campi):
                with cols[idx % 3]:
                    if campo == "Giri Motore":
                        scelte_utente["Giri_Motore"] = st.text_input(
                            "Giri Motore",
                            value=str(edit_data.get("Giri_Motore", "")) if edit_data else "",
                            key=f"giri_motore_thunderslot_{model_safe_key}",
                        )
                    else:
                        filtered = helper_filtra_pezzi_thunderslot(campo, thunder_components)
                        
                        if not filtered:
                            filtered = thunder_components
                        
                        opzioni = []
                        for p in filtered:
                            mat = str(p.get("Materiale") or "").strip()
                            mis = str(p.get("Misure") or "").strip()
                            if mat and mis:
                                opzioni.append(f"{mat} - {mis}")
                            elif mat:
                                opzioni.append(mat)
                            elif p.get("Prodotto"):
                                opzioni.append(str(p.get("Prodotto")).strip())
                            else:
                                opzioni.append("Componente senza nome")
                        
                        opzioni = list(dict.fromkeys(opzioni))
                        
                        if not opzioni:
                            opzioni = ["Nessun componente disponibile"]
                        
                        saved_val = edit_data.get(campo) if edit_data else None
                        idx_default = 0
                        if saved_val and saved_val in opzioni:
                            idx_default = opzioni.index(saved_val)
                        
                        scelte_utente[campo] = st.selectbox(
                            campo,
                            opzioni,
                            index=idx_default,
                            key=f"thunder_{campo}_{model_safe_key}",
                        )

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
                    key=f"thunder_sosp_{key_base}_sino_{model_safe_key}",
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
                      key=f"thunder_sosp_{key_base}_tipo_{model_safe_key}",
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
                        key=f"thunder_sosp_{key_base}_durezza_{model_safe_key}",
                    )
                    scelte_utente[f"Durezza_Molla_{tipo_sosp}"] = durezza_molla

            st.write("### 🏁 Gomme")
            col_gomme1, col_gomme2 = st.columns(2)
            with col_gomme1:
                sub_pezzi_gomme_ant = helper_filtra_pezzi("gomme anteriori", pezzi)
                scelte_utente["Gomme Anteriori"] = render_select_componente("Gomme Anteriori", sub_pezzi_gomme_ant, "gomme_ant_thunder")
            with col_gomme2:
                sub_pezzi_gomme_post = helper_filtra_pezzi("gomme posteriori", pezzi)
                scelte_utente["Gomme Posteriori"] = render_select_componente("Gomme Posteriori", sub_pezzi_gomme_post, "gomme_post_thunder")

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
                      value=str(edit_data.get("Giri_Motore", "")) if edit_data else "",
                      key=f"giri_motore_scaleauto_{model_safe_key}",
                  )
                elif campo == "Telaio":
                  modello_scaleauto = _normalizza_testo_filtro(selected_model_name)

                  alias_telaio_scaleauto = {
                      "audi r8 gt3": ["audi r8 lms"],
                      "bmw m8 gt": ["bmw m8 gtlm"],
                      "callaway gt3": ["callaway c7", "callaway gt3"],
                      "corvette c7r gt3": ["corvette c7r", "corvette c7.r"],
                      "honda nsx gt3": ["honda nsx gt3"],
                      "lmbh supertrofeo evo2": [
                          "lamborghini trofeo evo2",
                          "lbh supertrofeo evo2",
                          "supertrofeo evo2",
                      ],
                      "porsche 911/911.2 gt3": [
                          "porsche 911 gt3",
                          "porsche 911.2 gt3",
                      ],
                      "porsche p-963 gtp": [
                          "p-963 gtp",
                          "porsche 963 gtp",
                      ],
                  }

                  alias = alias_telaio_scaleauto.get(modello_scaleauto, [])
                  sub_pezzi = []

                  if alias:
                    for p in pezzi:
                      if not p or _normalizza_testo_filtro(p.get("Prodotto")) != "telaio":
                        continue

                      testo_telaio = " ".join(
                          filter(
                              None,
                              [
                                  _normalizza_testo_filtro(p.get("Materiale")),
                                  _normalizza_testo_filtro(p.get("Misure")),
                              ],
                          )
                      )

                      if any(
                          _normalizza_testo_filtro(a) in testo_telaio
                          for a in alias
                      ):
                        sub_pezzi.append(p)

                  scelte_utente[campo] = render_select_componente(
                      campo, sub_pezzi, "scaleauto"
                  )

                else:
                  sub_pezzi = helper_filtra_pezzi(campo, pezzi)
                  scelte_utente[campo] = render_select_componente(campo, sub_pezzi, "scaleauto")

            st.write("### 🔩 Sospensioni Scaleauto")
            sosp_sc_opts = ["No", "Sì"]
            def_sosp_sc = edit_data.get("Sospensioni", "No") if edit_data else "No"
            idx_sosp_sc = sosp_sc_opts.index(def_sosp_sc) if def_sosp_sc in sosp_sc_opts else 0
            sosp_scaleauto_attive = st.selectbox(
                "Sospensioni",
                sosp_sc_opts,
                index=idx_sosp_sc,
                key=f"scaleauto_sosp_sino_{model_safe_key}",
            )
            scelte_utente["Sospensioni"] = sosp_scaleauto_attive
            if sosp_scaleauto_attive == "Sì":
              molla_sc_opts = ["Molle Hard", "Molle Medium", "Molle Soft"]
              def_molla_sc = edit_data.get("Tipo_Molla_Scaleauto", "Molle Hard") if edit_data else "Molle Hard"
              idx_molla_sc = molla_sc_opts.index(def_molla_sc) if def_molla_sc in molla_sc_opts else 0
              scelte_utente["Tipo_Molla_Scaleauto"] = st.selectbox(
                  "Tipo Molla",
                  molla_sc_opts,
                  index=idx_molla_sc,
                  key=f"scaleauto_tipo_molla_{model_safe_key}",
              )

            st.write("### 🏁 Gomme")
            col_gomme1, col_gomme2 = st.columns(2)
            with col_gomme1:
                sub_pezzi_gomme_ant = helper_filtra_pezzi("gomme anteriori", pezzi)
                scelte_utente["Gomme Anteriori"] = render_select_componente("Gomme Anteriori", sub_pezzi_gomme_ant, "gomme_ant_scaleauto")
            with col_gomme2:
                sub_pezzi_gomme_post = helper_filtra_pezzi("gomme posteriori", pezzi)
                scelte_utente["Gomme Posteriori"] = render_select_componente("Gomme Posteriori", sub_pezzi_gomme_post, "gomme_post_scaleauto")

          else:
            priorita = ["Motore", "Corona Sidewinder", "Pignone"]
            altre_tipologie = [
                t for t in list(set([p.get("Prodotto") for p in pezzi if p and p.get("Prodotto")]))
                if t not in priorita
                and t not in ["Sospensioni", "Cuscinetti a flangia sin", "Bronzine"]
                and "distanzial" not in t.lower()
            ]
            tutte_le_principali = [p for p in priorita if any(x and x.get("Prodotto") == p for x in pezzi)] + altre_tipologie

            cols = st.columns(3)
            for i, tipologia in enumerate(tutte_le_principali):
              sub_pezzi = [p for p in pezzi if p and p.get("Prodotto") == tipologia]
              with cols[i % 3]:
                scelte_utente[tipologia] = render_select_componente(tipologia, sub_pezzi, "comp")

            st.write("### 🏁 Gomme")
            col_gomme1, col_gomme2 = st.columns(2)
            with col_gomme1:
                scelte_utente["Gomme Anteriori"] = st.text_input(
                    "Gomme Anteriori",
                    value=str(edit_data.get("Gomme Anteriori", "")) if edit_data else "",
                    key=f"gomme_ant_altri_{model_safe_key}"
                )
            with col_gomme2:
                scelte_utente["Gomme Posteriori"] = st.text_input(
                    "Gomme Posteriori",
                    value=str(edit_data.get("Gomme Posteriori", "")) if edit_data else "",
                    key=f"gomme_post_altri_{model_safe_key}"
                )

        st.divider()
        st.write("### 📏 Altezze e Quote")
        col_alt1, col_alt2 = st.columns(2)
        with col_alt1:
          scelte_utente["Altezza_Telaio"] = st.text_input(
              "Altezza Telaio",
              value=str(edit_data.get("Altezza_Telaio", "")) if edit_data else "",
              key=f"altezza_telaio_{model_safe_key}"
          )
        with col_alt2:
          scelte_utente["Altezza_boccole"] = st.text_input(
              "Altezza boccole",
              value=str(edit_data.get("Altezza_boccole", "")) if edit_data else "",
              key=f"altezza_boccole_{model_safe_key}"
          )

        st.divider()

        if selected_prod_name == "Altri Produttori":
          pass
        elif selected_prod_name.lower() == "slot.it":
          st.write("### 📏 Distanziali")
          col_d_pick = st.columns(1)[0]
          with col_d_pick:
            dp_opts = ["No", "Sì"]
            def_dp = edit_data.get("Distanziali_Pickup", "No") if edit_data else "No"
            idx_dp = dp_opts.index(def_dp) if def_dp in dp_opts else 0
            dist_pick_attive = st.selectbox(
                "Distanziale Pickup",
                dp_opts,
                index=idx_dp,
                key=f"dist_pick_si_no_{model_safe_key}",
            )
            scelte_utente["Distanziali_Pickup"] = dist_pick_attive
            if dist_pick_attive == "Sì":
              lista_dist_pick = [
                  p for p in pezzi
                  if p and p.get("Prodotto") and p.get("Prodotto").strip().lower() == "distanziale pickup"
              ]
              scelte_utente["Distanziale_Pickup"] = render_select_componente("Distanziale_Pickup", lista_dist_pick, "sel_dist_pick")
        else:
          st.write("### 📏 Distanziali")
          col_d1, col_d2, col_d3 = st.columns(3)

          with col_d1:
            scelte_utente["Distanziale_alla_corona"] = st.text_input(
                "Distanziale alla corona",
                value=str(edit_data.get("Distanziale_alla_corona", "")) if edit_data else "",
                key=f"dist_corona_{model_safe_key}"
            )
          with col_d2:
            scelte_utente["Distanziale_alla_ruota"] = st.text_input(
                "Distanziale alla ruota",
                value=str(edit_data.get("Distanziale_alla_ruota", "")) if edit_data else "",
                key=f"dist_ruota_{model_safe_key}"
            )
          with col_d3:
            dpk_opts = ["No", "Sì"]
            def_dpk = edit_data.get("Distanziali_Pickup", "No") if edit_data else "No"
            idx_dpk = dpk_opts.index(def_dpk) if def_dpk in dpk_opts else 0
            dist_pick_attive = st.selectbox(
                "Distanziale Pickup",
                dpk_opts,
                index=idx_dpk,
                key=f"dist_pick_si_no_{model_safe_key}",
            )
            scelte_utente["Distanziali_Pickup"] = dist_pick_attive
            if dist_pick_attive == "Sì":
              lista_dist_pick = [
                  p for p in pezzi
                  if p and p.get("Prodotto") and p.get("Prodotto").strip().lower() == "distanziale pickup"
              ]
              scelte_utente["Distanziale_Pickup"] = render_select_componente("Distanziale_Pickup", lista_dist_pick, "sel_dist_pick")

        st.divider()

        st.write("### 🔩 Supporto Assale")
        if selected_prod_name.lower() in ["nsr", "scaleauto"]:
            scelte_utente["Tipo_Supporto"] = "Bronzine"
            lista_bronzine = [
                p for p in pezzi if p and p.get("Prodotto") and "bronz" in p.get("Prodotto").lower()
            ]
            scelte_utente["Dettaglio_Supporto"] = render_select_componente("Dettaglio_Supporto", lista_bronzine, "sel_bronzine")
        else:
            sup_opts = ["Bronzine", "Cuscinetti"]
            def_sup = edit_data.get("Tipo_Supporto", "Bronzine") if edit_data else "Bronzine"
            idx_sup = sup_opts.index(def_sup) if def_sup in sup_opts else 0
            scelta_tipo_supp = st.selectbox(
                "Seleziona componente",
                sup_opts,
                index=idx_sup,
                key=f"scelta_bronz_cusc_{model_safe_key}",
            )
            scelte_utente["Tipo_Supporto"] = scelta_tipo_supp

            if scelta_tipo_supp == "Bronzine":
                keywords_bronz = ["bronz", "bronzina"]
                lista_bronzine = []
                for p in pezzi:
                    if not p: continue
                    testo = " ".join([
                        str(p.get("Prodotto", "")),
                        str(p.get("Materiale", "")),
                        str(p.get("Misure", "")),
                        str(p.get("Tipo", ""))
                    ]).lower()
                    if any(kw in testo for kw in keywords_bronz):
                        lista_bronzine.append(p)
                if not lista_bronzine:
                    for p in catalogo_componenti:
                        if p and p.get("id_Produttori") == prod_id_selezionato:
                            testo = " ".join([
                                str(p.get("Prodotto", "")),
                                str(p.get("Materiale", "")),
                                str(p.get("Misure", "")),
                                str(p.get("Tipo", ""))
                            ]).lower()
                            if any(kw in testo for kw in keywords_bronz):
                                lista_bronzine.append(p)
                if not lista_bronzine:
                    st.warning("Nessuna bronzina trovata per questo produttore. Verifica il catalogo.")
                scelte_utente["Dettaglio_Supporto"] = render_select_componente("Dettaglio_Supporto", lista_bronzine, "sel_bronzine")
            else:
                keywords_cusc = ["cuscinett", "cusc", "bearing", "cuscino"]
                lista_cuscinetti = []
                for p in pezzi:
                    if not p: continue
                    testo = " ".join([
                        str(p.get("Prodotto", "")),
                        str(p.get("Materiale", "")),
                        str(p.get("Misure", "")),
                        str(p.get("Tipo", ""))
                    ]).lower()
                    if any(kw in testo for kw in keywords_cusc):
                        lista_cuscinetti.append(p)
                if not lista_cuscinetti:
                    for p in catalogo_componenti:
                        if p and p.get("id_Produttori") == prod_id_selezionato:
                            testo = " ".join([
                                str(p.get("Prodotto", "")),
                                str(p.get("Materiale", "")),
                                str(p.get("Misure", "")),
                                str(p.get("Tipo", ""))
                            ]).lower()
                            if any(kw in testo for kw in keywords_cusc):
                                lista_cuscinetti.append(p)
                if not lista_cuscinetti:
                    st.warning("Nessun cuscinetto trovato per questo produttore. Verifica il catalogo.")
                scelte_utente["Dettaglio_Supporto"] = render_select_componente("Dettaglio_Supporto", lista_cuscinetti, "sel_cuscinetti")

        st.divider()

        scelte_utente["Note"] = st.text_area(
            "Note",
            value=str(edit_data.get("Note", "")) if edit_data else "",
            height=120,
            key=f"note_setup_generale_{model_safe_key}",
        )

        if foto_personalizzata_finale:
          scelte_utente["foto_personalizzata_url"] = foto_personalizzata_finale

        st.divider()

        st.markdown("### 📥 Nome Configurazione")
        
        nome_configurazione_input = st.text_input(
            "Nome Configurazione (es. Corvette Monza Gara)",
            value=st.session_state.get("modifying_config_name", ""),
            key=f"nome_config_{model_safe_key}",
        )

        col_dl_pdf, col_sv_gar = st.columns(2)

        with col_dl_pdf:
          try:
            pdf_bytes = generate_pdf(
                nome_configurazione_input if nome_configurazione_input else selected_model_name,
                selected_model_name,
                scelte_utente,
                foto_url=foto_personalizzata_finale if foto_personalizzata_finale else default_foto_db,
                produttore_nome=selected_prod_name,
            )
            st.download_button(
                label="⬇️ Scarica PDF al volo",
                data=pdf_bytes,
                file_name=f"{(nome_configurazione_input or selected_model_name).replace(' ', '_')}_scheda_tecnica.pdf",
                mime="application/pdf",
                key=f"download_pdf_setup_{model_safe_key}",
            )
          except Exception as e:
            st.error(f"Errore generazione PDF: {e}")

        with col_sv_gar:
          if st.session_state.modifying_config_id:
            if st.button("💾 Salva Modifiche Configurazione"):
              if not st.session_state.user:
                st.session_state.pending_garage_data = {
                    "nome_configurazione": nome_configurazione_input,
                    "modello_nome": selected_model_name,
                    "dettagli_setup": scelte_utente,
                    "is_update": True,
                    "config_id": st.session_state.modifying_config_id
                }
                st.session_state.active_tab = "🚗 Il Mio Garage"
                st.rerun()
              else:
                if not nome_configurazione_input:
                  st.warning("Inserisci un nome per la configurazione.")
                else:
                  try:
                    telaio_catalogo_id = trova_telaio_catalogo_id(
                        scelte_utente.get("Telaio")
                    )

                    record_garage = {
                        "nome_configurazione": nome_configurazione_input,
                        "modello_nome": selected_model_name,
                        "dettagli_setup": serialize_details(scelte_utente),
                        "telaio_catalogo_id": telaio_catalogo_id,
                        "user_id": st.session_state.user.id
                    }
                    supabase.table("IlMioGarage").update(record_garage).eq(
                        "id", st.session_state.modifying_config_id
                    ).eq("user_id", st.session_state.user.id).execute()
                    st.success(f"Configurazione '{nome_configurazione_input}' aggiornata con successo!")
                    st.session_state.modifying_config_id = None
                    st.session_state.modifying_data = None
                    st.session_state.modifying_config_name = ""
                    if "modifying_model_name" in st.session_state:
                      del st.session_state.modifying_model_name
                    st.session_state.active_tab = "🚗 Il Mio Garage"
                    st.rerun()
                  except Exception as e:
                    st.error(f"Errore durante l'aggiornamento: {e}")
          else:
            if st.button("🚗 Salva nel mio garage"):
              if not nome_configurazione_input or not nome_configurazione_input.strip():
                st.warning("Inserisci un nome per la configurazione prima di salvare nel Garage.")
              elif not st.session_state.user:
                st.session_state.pending_garage_data = {
                    "nome_configurazione": nome_configurazione_input,
                    "modello_nome": selected_model_name,
                    "dettagli_setup": scelte_utente,
                    "is_update": False,
                    "config_id": None
                }
                st.session_state.active_tab = "🚗 Il Mio Garage"
                st.rerun()
              else:
                if not nome_configurazione_input:
                  st.warning("Inserisci un nome per la configurazione prima di salvare nel Garage.")
                else:
                  try:
                    telaio_catalogo_id = trova_telaio_catalogo_id(
                        scelte_utente.get("Telaio")
                    )

                    record_garage = {
                        "nome_configurazione": nome_configurazione_input,
                        "modello_nome": selected_model_name,
                        "dettagli_setup": serialize_details(scelte_utente),
                        "telaio_catalogo_id": telaio_catalogo_id,
                        "user_id": st.session_state.user.id
                    }
                    supabase.table("IlMioGarage").insert(record_garage).execute()
                    st.success(f"Configurazione '{nome_configurazione_input}' salvata con successo nel tuo Garage!")
                    st.session_state.active_tab = "🚗 Il Mio Garage"
                    st.rerun()
                  except Exception as e:
                    st.error(f"Errore durante il salvataggio nel Garage: {e}")

        if st.session_state.modifying_config_id:
          if st.button("❌ Annulla Modifica"):
            st.session_state.modifying_config_id = None
            st.session_state.modifying_data = None
            st.session_state.modifying_config_name = ""
            if "modifying_model_name" in st.session_state:
              del st.session_state.modifying_model_name
            st.session_state.active_tab = "🚗 Il Mio Garage"
            st.rerun()

      else:
        st.info(
            "Seleziona prima un produttore specifico nei filtri in alto per"
            " accedere al setup avanzato."
        )
  else:
    st.info("Seleziona un modello tra i filtri in alto per configurarlo.")

elif st.session_state.active_tab == "🚗 Il Mio Garage":
  st.subheader("🚗 Il Mio Garage - Configurazioni Salvate")

  # ============================================================
  # PUNTO 2: DASHBOARD STATISTICHE
  # ============================================================
  if st.session_state.user:
    try:
        configs = supabase.table("IlMioGarage").select("id", count="exact").eq("user_id", st.session_state.user.id).execute()
        tot_configs = configs.count if hasattr(configs, 'count') else len(configs.data or [])
        
        modelli_count = {}
        for c in (configs.data or []):
            modello = c.get("modello_nome", "Sconosciuto")
            modelli_count[modello] = modelli_count.get(modello, 0) + 1
        modello_piu_usato = max(modelli_count, key=modelli_count.get) if modelli_count else "Nessuno"
        
        prove = supabase.table("SlotGarage_Prove").select("miglior_tempo").eq("user_id", st.session_state.user.id).execute()
        miglior_tempo = None
        for p in (prove.data or []):
            tm = p.get("miglior_tempo")
            if tm is not None and (miglior_tempo is None or tm < miglior_tempo):
                miglior_tempo = tm
        
        piste_count = {}
        for p in (prove.data or []):
            pista = p.get("pista", "Sconosciuta")
            piste_count[pista] = piste_count.get(pista, 0) + 1
        pista_preferita = max(piste_count, key=piste_count.get) if piste_count else "Nessuna"
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("📦 Configurazioni", tot_configs)
        with col2:
            st.metric("🏆 Modello preferito", modello_piu_usato)
        with col3:
            st.metric("⏱️ Miglior tempo", f"{miglior_tempo:.3f}s" if miglior_tempo else "—")
        with col4:
            st.metric("🏁 Pista preferita", pista_preferita)
        st.divider()
    except Exception as e:
        st.warning(f"Impossibile caricare statistiche: {e}")

  # ============================================================
  # PUNTO 3A: IMPORTA JSON
  # ============================================================
  if st.session_state.user:
    with st.expander("📥 Importa configurazione da JSON"):
        uploaded_file = st.file_uploader("Seleziona file JSON", type=["json"], key="import_json_uploader")
        if uploaded_file is not None:
            try:
                data = json.load(uploaded_file)
                record = {
                    "nome_configurazione": data.get("nome_configurazione", "Importata"),
                    "modello_nome": data.get("modello_nome", "Modello importato"),
                    "dettagli_setup": data.get("dettagli_setup", {}),
                    "telaio_catalogo_id": data.get("telaio_catalogo_id"),
                    "user_id": st.session_state.user.id
                }
                supabase.table("IlMioGarage").insert(record).execute()
                st.success("✅ Configurazione importata con successo!")
                st.rerun()
            except Exception as e:
                st.error(f"Errore durante l'importazione: {e}")

  if not st.session_state.user:
    st.info("Accedi o registrati per visualizzare e gestire il tuo garage personale.")
    richiedi_autenticazione()
  else:
    try:
      response_garage = supabase.table("IlMioGarage").select("*").eq("user_id", st.session_state.user.id).execute()
      salvati = response_garage.data if response_garage and response_garage.data else []

      if salvati:
        for s in salvati:
          if not s:
            continue
          conf_id = s.get("id")
          conf_nome = s.get(
              "nome_configurazione", "Configurazione senza nome"
          )
          conf_modello = s.get("modello_nome", "Modello non specificato")

          dettagli_str = s.get("dettagli_setup", "{}")
          dict_dettagli = {}
          dict_dettagli = deserialize_details(dettagli_str)

          foto_auto_url = None
          prod_nome_per_pdf = ""
          if (
              isinstance(dict_dettagli, dict)
              and dict_dettagli.get("foto_personalizzata_url")
          ):
            foto_auto_url = dict_dettagli.get("foto_personalizzata_url")
          else:
            match_modello = next(
                (m for m in modelli if m and m.get("name") == conf_modello), None
            )
            foto_auto_url = (
                match_modello.get("foto_url") if match_modello else None
            )
          
          match_modello_obj = next((m for m in modelli if m and m.get("name") == conf_modello), None)
          if match_modello_obj:
            cat_id_m = match_modello_obj.get("category_id")
            cat_obj_m = next((c for c in categorie if c and c.get("id") == cat_id_m), None)
            if cat_obj_m:
              brand_id_m = cat_obj_m.get("brand_it")
              prod_obj_m = next((p for p in produttori if p and p.get("id") == brand_id_m), None)
              if prod_obj_m:
                prod_nome_per_pdf = prod_obj_m.get("name", "")

          col_info, col_btn_pdf, col_btn_mod, col_btn_del, col_btn_export = st.columns(
              [4, 2, 2, 2, 2]
          )
          with col_info:
            st.markdown(
                f"**🏎️ {conf_nome}** — *(Modello: {conf_modello})*"
          )

          with col_btn_pdf:
            try:
              pdf_bytes = generate_pdf(
                  conf_nome,
                  conf_modello,
                  (
                      dict_dettagli
                      if isinstance(dict_dettagli, dict)
                      else {"Dettagli": dettagli_str}
                  ),
                  foto_url=foto_auto_url,
                  produttore_nome=prod_nome_per_pdf,
              )
              st.download_button(
                  label="⬇️ PDF",
                  data=pdf_bytes,
                  file_name=f"{conf_nome.replace(' ', '_')}_scheda_tecnica.pdf",
                  mime="application/pdf",
                  key=f"download_pdf_{conf_id}",
              )
            except Exception as e:
              st.error(f"Errore PDF: {e}")

          with col_btn_mod:
            if st.button("✏️ Modifica", key=f"edit_conf_{conf_id}"):
              st.session_state.modifying_config_id = conf_id
              st.session_state.modifying_config_name = conf_nome
              st.session_state.modifying_model_name = conf_modello
              dettagli_str_init = s.get("dettagli_setup", "{}")
              st.session_state.modifying_data = deserialize_details(dettagli_str_init)
              st.session_state.active_tab = "📋 Visualizza Modelli"
              st.rerun()

          with col_btn_del:
            if st.button("🗑️ Elimina", key=f"del_conf_{conf_id}"):
              try:
                supabase.table("IlMioGarage").delete().eq(
                    "id", conf_id
                ).eq("user_id", st.session_state.user.id).execute()
                st.success("Configurazione eliminata con successo!")
                st.rerun()
              except Exception as e:
                st.error(f"Errore durante l'eliminazione: {e}")

          # ============================================================
          # PUNTO 3B: ESPORTA JSON
          # ============================================================
          with col_btn_export:
            export_data = {
                "nome_configurazione": conf_nome,
                "modello_nome": conf_modello,
                "dettagli_setup": dict_dettagli if isinstance(dict_dettagli, dict) else {},
                "telaio_catalogo_id": s.get("telaio_catalogo_id"),
            }
            json_str = json.dumps(export_data, ensure_ascii=False, indent=2)
            st.download_button(
                label="📤 JSON",
                data=json_str,
                file_name=f"{conf_nome.replace(' ', '_')}.json",
                mime="application/json",
                key=f"export_json_{conf_id}"
            )

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

elif st.session_state.active_tab == "🎛️ Il Mio Pulsante":
  st.subheader("🎛️ Gestione Il Mio Pulsante")
  st.write(
      "Configura le impostazioni e i parametri tecnici del tuo pulsante di"
      " guida."
  )

  pulsante_edit = st.session_state.modifying_pulsante_data if st.session_state.modifying_pulsante_id else {}
  
  if st.session_state.modifying_pulsante_id:
    st.info("Stai modificando un pulsante esistente.")

  def_tipo_pulsante = pulsante_edit.get("Tipo Pulsante", "Analogico") if pulsante_edit else "Analogico"
  idx_tipo = 0 if def_tipo_pulsante == "Analogico" else 1

  col_bp1, col_bp2, col_bp3 = st.columns(3)
  with col_bp1:
    scelta_tipo_pulsante = st.selectbox(
        "Seleziona Tipo Pulsante", ["Analogico", "Digitale"], index=idx_tipo
    )

  scelta_modello_analogico = None
  scelta_modello_digitale = None
  if scelta_tipo_pulsante == "Analogico":
    with col_bp2:
      modelli_analogici_list = ["Savatteri", "Santagati", "Altro"]
      def_mod_an = pulsante_edit.get("Modello Specifico", "Savatteri") if pulsante_edit else "Savatteri"
      idx_mod_an = modelli_analogici_list.index(def_mod_an) if def_mod_an in modelli_analogici_list else 0
      scelta_modello_analogico = st.selectbox(
          "Seleziona Modello Analogico", modelli_analogici_list, index=idx_mod_an
      )
  elif scelta_tipo_pulsante == "Digitale":
    with col_bp2:
      modelli_digitali_list = [
          "Tic Tac",
          "C.O.S.A",
          "SLOT.IT SCP-1",
          "SLOT.IT SCP-2",
          "SLOT.IT SCP-3",
          "SLOTING PLUS",
      ]
      def_mod_dig = pulsante_edit.get("Modello Specifico", "Tic Tac") if pulsante_edit else "Tic Tac"
      idx_mod_dig = modelli_digitali_list.index(def_mod_dig) if def_mod_dig in modelli_digitali_list else 0
      scelta_modello_digitale = st.selectbox(
          "Seleziona Modello Digitale",
          modelli_digitali_list,
          index=idx_mod_dig
      )

  with col_bp3:
    piste_list = ["Ninco", "Policar", "Carrera", "Scaleauto", "Legno", "Fero"]
    def_pista = pulsante_edit.get("Tipo Pista", "Ninco") if pulsante_edit else "Ninco"
    idx_pista = piste_list.index(def_pista) if def_pista in piste_list else 0
    tipo_pista_val = st.selectbox(
        "Tipo Pista", piste_list, index=idx_pista
    )

  tipo_auto_val = st.text_input("Tipo Auto (Modello)", value=pulsante_edit.get("Tipo Auto", "") if pulsante_edit else "")

  st.divider()
  st.markdown("### ⚙️ Parametri Tecnici del Pulsante")

  if scelta_tipo_pulsante == "Digitale" and scelta_modello_digitale == "Tic Tac":
      col_tp1, col_tp2 = st.columns(2)
      with col_tp1:
          mappa_potenza_opts = [str(i) for i in range(1, 5)]
          def_mappa = str(pulsante_edit.get("Mappa Potenza", "1")) if pulsante_edit else "1"
          idx_mappa = mappa_potenza_opts.index(def_mappa) if def_mappa in mappa_potenza_opts else 0
          mappa_potenza_val = st.selectbox("Mappa Potenza", mappa_potenza_opts, index=idx_mappa)

          potenza_val = st.text_input("Potenza", value=pulsante_edit.get("Potenza", "") if pulsante_edit else "")
          tipo_freno_val = st.text_input("Tipo Freno", value=pulsante_edit.get("Tipo Freno", "") if pulsante_edit else "")
      with col_tp2:
          valore_freno_val = st.text_input("Valore Freno", value=pulsante_edit.get("Valore Freno", "") if pulsante_edit else "")
          sensibilita_grilletto_val = st.text_input("Sensibilità Grilletto", value=pulsante_edit.get("Sensibilità Grilletto", "") if pulsante_edit else "")
          antispin_val = st.text_input("Antispin", value=pulsante_edit.get("Antispin", "") if pulsante_edit else "")

          min_speed_val = ""
          curve_val = ""
          freno_val = ""
          power_trim_val = ""
          mapping_val = ""
          ohm_val = ""
          sensibilita_val = ""
          start_val = ""
          curva_potenza_val = ""
          freno_fine_rettilineo_val = ""
          resistenza_val = ""
          tasto_spunto_val = ""
          tasto_freno_val = ""
          tuning_val = ""
          th_min_val = ""
          th_max_val = ""

  elif scelta_tipo_pulsante == "Digitale" and scelta_modello_digitale in ["SLOT.IT SCP-1", "SLOT.IT SCP-2", "SLOT.IT SCP-3"]:
      col_tp1, col_tp2 = st.columns(2)
      with col_tp1:
          min_speed_val = st.text_input("Min Speed", value=pulsante_edit.get("Min Speed", "") if pulsante_edit else "")
          curve_val = st.text_input("Curve", value=pulsante_edit.get("Curve", "") if pulsante_edit else "")
          freno_val = st.text_input("Freno", value=pulsante_edit.get("Freno", "") if pulsante_edit else "")
      with col_tp2:
          power_trim_val = st.text_input("Power Trim", value=pulsante_edit.get("Power Trim", "") if pulsante_edit else "")
          mapping_opts = ["Slow", "Normal", "Fast"]
          def_mapping = pulsante_edit.get("Mapping", "Normal") if pulsante_edit else "Normal"
          idx_mapping = mapping_opts.index(def_mapping) if def_mapping in mapping_opts else 1
          mapping_val = st.selectbox("Mapping", mapping_opts, index=idx_mapping)
          
          mappa_potenza_val = ""
          potenza_val = ""
          tipo_freno_val = ""
          valore_freno_val = ""
          sensibilita_grilletto_val = ""
          ohm_val = ""
          antispin_val = ""
          sensibilita_val = ""
          start_val = ""
          curva_potenza_val = ""
          freno_fine_rettilineo_val = ""
          resistenza_val = ""
          tasto_spunto_val = ""
          tasto_freno_val = ""
          tuning_val = ""
          th_min_val = ""
          th_max_val = ""

  elif scelta_tipo_pulsante == "Digitale" and scelta_modello_digitale == "C.O.S.A":
      col_tp1, col_tp2 = st.columns(2)
      with col_tp1:
          tuning_val = st.text_input("Tuning", value=pulsante_edit.get("Tuning", "") if pulsante_edit else "")
          sensibilita_val = st.text_input("Sensibilità", value=pulsante_edit.get("Sensibilità", "") if pulsante_edit else "")
      with col_tp2:
          freno_val = st.text_input("Freno", value=pulsante_edit.get("Freno", "") if pulsante_edit else "")
          th_min_val = st.text_input("TH MIN", value=pulsante_edit.get("TH MIN", "") if pulsante_edit else "")
          th_max_val = st.text_input("TH MAX", value=pulsante_edit.get("TH MAX", "") if pulsante_edit else "")

          mappa_potenza_val = ""
          potenza_val = ""
          tipo_freno_val = ""
          valore_freno_val = ""
          sensibilita_grilletto_val = ""
          min_speed_val = ""
          curve_val = ""
          power_trim_val = ""
          mapping_val = ""
          ohm_val = ""
          antispin_val = ""
          start_val = ""
          curva_potenza_val = ""
          freno_fine_rettilineo_val = ""
          resistenza_val = ""
          tasto_spunto_val = ""
          tasto_freno_val = ""

  elif scelta_tipo_pulsante == "Digitale" and scelta_modello_digitale == "SLOTING PLUS":
      col_tp1, col_tp2 = st.columns(2)
      with col_tp1:
          freno_val = st.text_input("Freno", value=pulsante_edit.get("Freno", "") if pulsante_edit else "")
          sensibilita_val = st.text_input("Sensibilità", value=pulsante_edit.get("Sensibilità", "") if pulsante_edit else "")
          start_val = st.text_input("Start", value=pulsante_edit.get("Start", "") if pulsante_edit else "")
      with col_tp2:
          antispin_val = st.text_input("Antispin", value=pulsante_edit.get("Antispin", "") if pulsante_edit else "")
          
          curva_potenza_opts = [str(i) for i in range(1, 10)]
          def_curva_pot = pulsante_edit.get("Curva di Potenza", "1") if pulsante_edit else "1"
          idx_curva_pot = curva_potenza_opts.index(def_curva_pot) if def_curva_pot in curva_potenza_opts else 0
          curva_potenza_val = st.selectbox("Curva di Potenza", curva_potenza_opts, index=idx_curva_pot)
          
          freno_fine_rettilineo_opts = ["On", "Off"]
          def_freno_rett = pulsante_edit.get("Freno di fine Rettilineo", "Off") if pulsante_edit else "Off"
          idx_freno_rett = freno_fine_rettilineo_opts.index(def_freno_rett) if def_freno_rett in freno_fine_rettilineo_opts else 1
          freno_fine_rettilineo_val = st.selectbox("Freno di fine Rettilineo", freno_fine_rettilineo_opts, index=idx_freno_rett)

          mappa_potenza_val = ""
          potenza_val = ""
          tipo_freno_val = ""
          valore_freno_val = ""
          sensibilita_grilletto_val = ""
          min_speed_val = ""
          curve_val = ""
          power_trim_val = ""
          mapping_val = ""
          ohm_val = ""
          resistenza_val = ""
          tasto_spunto_val = ""
          tasto_freno_val = ""
          tuning_val = ""
          th_min_val = ""
          th_max_val = ""

  else:
      col_tp1, col_tp2, col_tp3 = st.columns(3)

      with col_tp1:
        ohm_val = st.text_input("Ohm", value=pulsante_edit.get("Ohm", "") if pulsante_edit else "")
        antispin_val = st.text_input("Antispin", value=pulsante_edit.get("Antispin", "") if pulsante_edit else "")
        sensibilita_val = st.text_input("Sensibilità", value=pulsante_edit.get("Sensibilità", "") if pulsante_edit else "")

      with col_tp2:
        freno_val = st.text_input("Freno", value=pulsante_edit.get("Freno", "") if pulsante_edit else "")
        
        tasto_spunto_opts = ["Su", "Giu"]
        def_spunto = pulsante_edit.get("Tasto Spunto", "Su") if pulsante_edit else "Su"
        idx_spunto = tasto_spunto_opts.index(def_spunto) if def_spunto in tasto_spunto_opts else 0
        tasto_spunto_val = st.selectbox("Tasto Spunto", tasto_spunto_opts, index=idx_spunto)
        
        tasto_freno_opts = ["Tutto Freno", "Valori Potenziometro"]
        def_freno_tasto = pulsante_edit.get("Tasto Freno", "Tutto Freno") if pulsante_edit else "Tutto Freno"
        idx_freno_tasto = tasto_freno_opts.index(def_freno_tasto) if def_freno_tasto in tasto_freno_opts else 0
        tasto_freno_val = st.selectbox(
            "Tasto Freno", tasto_freno_opts, index=idx_freno_tasto
        )

      with col_tp3:
        resistenza_val = st.text_input("Resistenza", value=pulsante_edit.get("Resistenza", "") if pulsante_edit else "")
        min_speed_val = ""
        curve_val = ""
        power_trim_val = ""
        mapping_val = ""
        start_val = ""
        curva_potenza_val = ""
        freno_fine_rettilineo_val = ""
        mappa_potenza_val = ""
        potenza_val = ""
        tipo_freno_val = ""
        valore_freno_val = ""
        sensibilita_grilletto_val = ""
        tuning_val = ""
        th_min_val = ""
        th_max_val = ""

  st.divider()
  
  default_nome_pulsante = "Mio Pulsante"
  if st.session_state.modifying_pulsante_id and "modifying_pulsante_name" in st.session_state:
    default_nome_pulsante = st.session_state.modifying_pulsante_name

  nome_config_pulsante = st.text_input(
      "Nome Configurazione Pulsante", value=default_nome_pulsante
  )

  if st.session_state.modifying_pulsante_id:
    col_m1, col_m2 = st.columns(2)
    with col_m1:
      if st.button("💾 Aggiorna Impostazioni Pulsante"):
        if not st.session_state.user:
          richiedi_autenticazione()
        else:
          if not nome_config_pulsante:
            st.warning("Inserisci un nome per la configurazione del pulsante.")
          else:
            try:
              dati_pulsante = {
                  "Tipo Pulsante": scelta_tipo_pulsante,
                  "Modello Specifico": (
                      scelta_modello_analogico
                      if scelta_tipo_pulsante == "Analogico"
                      else scelta_modello_digitale
                  ),
                  "Tipo Pista": tipo_pista_val,
                  "Tipo Auto": tipo_auto_val,
                  "Ohm": ohm_val,
                  "Antispin": antispin_val,
                  "Sensibilità": sensibilita_val,
                  "Freno": freno_val,
                  "Tasto Spunto": tasto_spunto_val,
                  "Tasto Freno": tasto_freno_val,
                  "Resistenza": resistenza_val,
                  "Min Speed": min_speed_val,
                  "Curve": curve_val,
                  "Power Trim": power_trim_val,
                  "Mapping": mapping_val,
                  "Start": start_val,
                  "Curva di Potenza": curva_potenza_val,
                  "Freno di fine Rettilineo": freno_fine_rettilineo_val,
                  "Mappa Potenza": mappa_potenza_val,
                  "Potenza": potenza_val,
                  "Tipo Freno": tipo_freno_val,
                  "Valore Freno": valore_freno_val,
                  "Sensibilità Grilletto": sensibilita_grilletto_val,
                  "Tuning": tuning_val,
                  "TH MIN": th_min_val,
                  "TH MAX": th_max_val,
              }
              record_pulsante = {
                  "nome_configurazione": nome_config_pulsante,
                  "tipo_pulsante": scelta_tipo_pulsante,
                  "dettagli_setup": serialize_details(dati_pulsante),
                  "user_id": st.session_state.user.id
              }
              supabase.table("ilMioPulsante").update(record_pulsante).eq(
                  "id", st.session_state.modifying_pulsante_id
              ).eq("user_id", st.session_state.user.id).execute()
              st.success(f"Pulsante '{nome_config_pulsante}' aggiornato con successo!")
              st.session_state.modifying_pulsante_id = None
              st.session_state.modifying_pulsante_data = None
              st.rerun()
            except Exception as e:
              st.error(f"Errore durante l'aggiornamento del pulsante: {e}")
    with col_m2:
      if st.button("❌ Annulla Modifica Pulsante"):
        st.session_state.modifying_pulsante_id = None
        st.session_state.modifying_pulsante_data = None
        st.rerun()
  else:
    if st.button("💾 Salva Impostazioni Pulsante"):
      if not st.session_state.user:
        richiedi_autenticazione()
      else:
        if not nome_config_pulsante:
          st.warning("Inserisci un nome per la configurazione del pulsante.")
        else:
          try:
            dati_pulsante = {
                "Tipo Pulsante": scelta_tipo_pulsante,
                "Modello Specifico": (
                    scelta_modello_analogico
                    if scelta_tipo_pulsante == "Analogico"
                    else scelta_modello_digitale
                ),
                "Tipo Pista": tipo_pista_val,
                "Tipo Auto": tipo_auto_val,
                "Ohm": ohm_val,
                "Antispin": antispin_val,
                "Sensibilità": sensibilita_val,
                "Freno": freno_val,
                "Tasto Spunto": tasto_spunto_val,
                "Tasto Freno": tasto_freno_val,
                "Resistenza": resistenza_val,
                "Min Speed": min_speed_val,
                "Curve": curve_val,
                "Power Trim": power_trim_val,
                "Mapping": mapping_val,
                "Start": start_val,
                "Curva di Potenza": curva_potenza_val,
                "Freno di fine Rettilineo": freno_fine_rettilineo_val,
                "Mappa Potenza": mappa_potenza_val,
                "Potenza": potenza_val,
                "Tipo Freno": tipo_freno_val,
                "Valore Freno": valore_freno_val,
                "Sensibilità Grilletto": sensibilita_grilletto_val,
                "Tuning": tuning_val,
                "TH MIN": th_min_val,
                "TH MAX": th_max_val,
            }
            record_pulsante = {
                "nome_configurazione": nome_config_pulsante,
                "tipo_pulsante": scelta_tipo_pulsante,
                "dettagli_setup": serialize_details(dati_pulsante),
                "user_id": st.session_state.user.id
            }
            supabase.table("ilMioPulsante").insert(record_pulsante).execute()
            st.success(
                f"Configurazione del pulsante '{nome_config_pulsante}' salvata con"
                " successo nella tabella ilMioPulsante!"
            )
            st.rerun()
          except Exception as e:
            st.error(f"Errore durante il salvataggio del pulsante: {e}")

  st.divider()
  st.subheader("📋 I Tuoi Pulsanti Salvati")
  if not st.session_state.user:
    st.info("Accedi o registrati per visualizzare i tuoi pulsanti salvati.")
    richiedi_autenticazione()
  else:
    try:
      response_pulsanti = supabase.table("ilMioPulsante").select("*").eq("user_id", st.session_state.user.id).execute()
      elenco_pulsanti = response_pulsanti.data if response_pulsanti and response_pulsanti.data else []

      if elenco_pulsanti:
        for pul in elenco_pulsanti:
          if not pul:
            continue
          p_id = pul.get("id")
          p_nome = pul.get("nome_configurazione", "Pulsante senza nome")
          p_tipo = pul.get("tipo_pulsante", "N/D")
          
          p_dettagli_str = pul.get("dettagli_setup", "{}")
          p_dict = {}
          p_dict = deserialize_details(p_dettagli_str)

          col_p_info, col_p_mod, col_p_del = st.columns([6, 2, 2])
          with col_p_info:
            st.markdown(f"**🎛️ {p_nome}** — *(Tipo: {p_tipo})*")

          with col_p_mod:
            if st.button("✏️ Modifica", key=f"edit_pulsante_{p_id}"):
              st.session_state.modifying_pulsante_id = p_id
              st.session_state.modifying_pulsante_name = p_nome
              st.session_state.modifying_pulsante_data = p_dict
              st.rerun()

          with col_p_del:
            if st.button("🗑️ Elimina", key=f"del_pulsante_{p_id}"):
              try:
                supabase.table("ilMioPulsante").delete().eq("id", p_id).eq("user_id", st.session_state.user.id).execute()
                st.success("Pulsante eliminato con successo!")
                st.rerun()
              except Exception as e:
                st.error(f"Errore durante l'eliminazione: {e}")

          with st.expander(f"Dettagli tecnici di {p_nome}"):
            if isinstance(p_dict, dict):
              for k, v in p_dict.items():
                if v:
                  st.write(f"- **{k}:** {v}")
            else:
              st.write(p_dettagli_str)

          st.markdown("---")
      else:
        st.info("Nessuna configurazione di pulsante salvata al momento.")
    except Exception as e:
      st.error(f"Errore durante il recupero dei pulsanti: {e}")

elif st.session_state.active_tab == "➕ Carica Modello":
  st.subheader("Inserisci Nuovo Modello")
  with st.form("form_nuovo_modello"):
    nuovo_modello = st.text_input("Nome Modello")

    st.write("### Immagine di Default del Modello")
    carica_file_foto = st.file_uploader(
        "Carica immagine dal dispositivo", type=["jpg", "jpeg", "png"]
    )
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
      if not st.session_state.user:
        richiedi_autenticazione()
      elif nuovo_modello:
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
              "foto_url": finale_foto_url,
          }
          supabase.table("MODELLI").insert(nuovo_record).execute()
          st.cache_data.clear()
          st.success(f"Modello '{nuovo_modello}' salvato con successo!")
          st.rerun()
        except Exception as e:
          st.error(f"Errore durante il salvataggio: {e}")


# --- SLOTGARAGE PRO: voce di navigazione reale ---
if st.session_state.active_tab == "Comparazione e Telemetria Modelli":
  sg_pro_ui()
