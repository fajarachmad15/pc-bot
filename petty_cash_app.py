import os
import streamlit as st
import gspread
import pandas as pd
import google.generativeai as genai

# ==========================================================
# === KONFIGURASI HALAMAN ===
# ==========================================================
st.set_page_config(page_title="Asisten Kasir Petty Cash", layout="wide")

# ==========================================================
# === FUNGSI LOGIN ===
# ==========================================================
def login_form():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        run_coa_bot()
    else:
        st.title("🔒 Silakan Login")
        st.write("Masukkan kredensial untuk mengakses Asisten Kasir Petty Cash.")

        with st.form("login_form"):
            username = st.text_input("Username", placeholder="Username Anda")
            password = st.text_input("Password", type="password", placeholder="Password Anda")
            submitted = st.form_submit_button("Login")

            if submitted:
                try:
                    correct_user = st.secrets["app_credentials"]["APP_USER"]
                    correct_pass = st.secrets["app_credentials"]["APP_PASS"]
                except KeyError:
                    st.error("Kredensial aplikasi belum di-setting di secrets.toml")
                    return

                if username == correct_user and password == correct_pass:
                    st.session_state.authenticated = True
                    st.success("Login berhasil! Memuat aplikasi...")
                    st.rerun()
                else:
                    st.error("Username atau Password salah.")

# ==========================================================
# === FUNGSI AMBIL DATA SHEETS (MENIRU PROMO BOT) ===
# ==========================================================
@st.cache_data(ttl=600)
def get_database_df(_gc, sheet_key):
    try:
        # Mengambil sheet index 0 (tab pertama)
        sheet = _gc.open_by_key(sheet_key).get_worksheet(0)
        df = pd.DataFrame(sheet.get_all_records())
        return df
    except Exception as e:
        st.error(f"❌ Gagal memuat data Sheets. Error: {e}")
        st.stop()

# ==========================================================
# === OTAK AI (LUWES & PINTAR) ===
# ==========================================================
def get_ai_recommendation(item, kegunaan, pph, df_database):
    # Ubah database menjadi string agar bisa dibaca AI
    db_string = df_database.to_csv(index=False)
    
    # Gunakan Gemini 1.5 Flash yang lebih canggih memahami sinonim
    model = genai.GenerativeModel("models/gemini-1.5-flash")
    
    # Prompt yang jauh lebih luwes, tidak menggunakan aturan Tahap-Tahap yang kaku
    gemini_prompt = f"""
    Kamu adalah Asisten Kasir cerdas. Tugasmu mencari akun COA yang tepat dari database di bawah ini.
    
    DATABASE COA:
    {db_string}
    
    INPUT KASIR:
    - Item dibeli: "{item}"
    - Digunakan untuk: "{kegunaan}"
    - Status PPh / Faktur Pajak: "{pph}"
    
    INSTRUKSI KERJA:
    1. Cari baris yang paling cocok secara semantik. Pahami sinonim! (Contoh: "Batagor" = Makanan, "Jaga Malam" = Lembur/Makan Staff, "Pulpen" = ATK).
    2. Jika input adalah ATK (Supplies), pastikan barangnya wajar untuk kantor.
    3. ATURAN PPH: Jika Status PPh adalah "Yes", maka kamu WAJIB:
       - Ubah Output COA menjadi "Pembayaran Pemasok"
       - Ubah Output No. G/L menjadi "N/A"
       - Tambahkan teks ini di AWAL bagian Catatan: "- NPWP PT / Badan potong PPh 2% dari DPP\\n- NPWP Perorangan potong PPh 2.5% dari DPP\\n"
    4. Jika data benar-benar melenceng dan tidak ada di database, jawab saja: "Saya tidak dapat menemukan akun yang cocok untuk item tersebut."
    
    FORMAT JAWABAN (WAJIB SEPERTI INI, JANGAN ADA TEKS LAIN):
    Rekomendasi COA: [Isi COA]
    No. G/L Account: [Isi G/L]
    Catatan: [Isi Remark/Catatan. Rapikan sedikit jika kepanjangan, tapi jangan hilangkan aturan penting]
    Approval: [Isi Approval]
    Budget: [Isi Budget]
    Profit Center: [Isi Profit Center]
    Cost Center: [Isi Cost Center]
    """

    try:
        response = model.generate_content(gemini_prompt)
        return response.text.strip()
    except Exception as e:
        return f"Terjadi error saat menghubungi AI: {e}"

# ==========================================================
# === APLIKASI UTAMA ===
# ==========================================================
def run_coa_bot():
    # --- 1. KONFIGURASI API & KREDENSIAL ---
    API_KEY = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not API_KEY:
        st.error("❌ API key Gemini tidak ditemukan.")
        st.stop()
    genai.configure(api_key=API_KEY)

    if "gcp_service_account" not in st.secrets:
        st.error("❌ Service account Google Sheets tidak ditemukan.")
        st.stop()

    try:
        gcp = dict(st.secrets["gcp_service_account"])
        gc = gspread.service_account_from_dict(gcp)
    except Exception as e:
        st.error(f"❌ Gagal memuat kredensial GCP: {e}")
        st.stop()

    SHEET_KEY = st.secrets.get("SHEET_KEY")
    if not SHEET_KEY:
        st.error("❌ SHEET_KEY tidak ditemukan.")
        st.stop()

    # --- 2. AMBIL DATABASE ---
    df_coa = get_database_df(gc, SHEET_KEY)

    # --- 3. TAMPILAN UI ---
    st.title("🤖 Asisten Kasir Petty Cash")
    st.write("Saya terhubung dengan 'Data Base COA' dan siap membantu Anda.")
    st.divider()
    
    st.header("🔍 Cari Rekomendasi Akun COA")
    st.write("Masukkan detail pengeluaran untuk menemukan COA yang tepat.")

    with st.form(key="search_form"):
        col1, col2 = st.columns(2)
        with col1:
            item_dibeli = st.text_input("Item yg dibeli:", placeholder="Contoh: Aqua Galon, Batagor...")
        with col2:
            digunakan_untuk = st.text_input("Digunakan Untuk:", placeholder="Contoh: Minum karyawan, Jaga malam...")
        
        pph_faktur = st.radio("Potong PPh / Dapat Faktur Pajak?", ("No", "Yes"), index=0, horizontal=True)
        submitted = st.form_submit_button("Cari Rekomendasi COA")

    if submitted:
        if not item_dibeli or not digunakan_untuk:
            st.warning("Mohon isi kedua kolom (Item & Digunakan Untuk).")
        else:
            with st.spinner("Menganalisa dan mencari COA yang tepat..."):
                hasil_ai = get_ai_recommendation(item_dibeli, digunakan_untuk, pph_faktur, df_coa)
                
                st.subheader("Hasil Rekomendasi:")
                # Menampilkan hasil baris per baris agar link URL bisa diklik
                for baris in hasil_ai.split('\n'):
                    if "http://" in baris or "https://" in baris:
                        st.markdown(baris)
                    else:
                        st.text(baris)

# ==========================================================
# === TITIK MASUK APLIKASI ===
# ==========================================================
login_form()