import os
import hmac
import streamlit as st
import gspread
import pandas as pd
from google import genai

# ==========================================================
# === KONFIGURASI HALAMAN ===
# HARUS diletakkan di bagian paling atas sebelum render Streamlit lainnya
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
                # Penanganan st.secrets yang aman dari KeyError/AttributeError
                app_creds = st.secrets.get("app_credentials", {})
                correct_user = app_creds.get("APP_USER")
                correct_pass = app_creds.get("APP_PASS")

                if not correct_user or not correct_pass:
                    st.error("❌ Kredensial (APP_USER / APP_PASS) belum dikonfigurasi di secrets.toml.")
                    return

                # Menggunakan timing-safe comparison untuk keamanan autentikasi
                if hmac.compare_digest(username, correct_user) and hmac.compare_digest(password, correct_pass):
                    st.session_state.authenticated = True
                    st.success("Login berhasil! Memuat aplikasi...")
                    st.rerun()
                else:
                    st.error("Username atau Password salah.")

# ==========================================================
# === FUNGSI AMBIL DATA SHEETS & CACHING ===
# ==========================================================
@st.cache_data(ttl=600)
def get_database_df(gcp_dict, sheet_key):
    """
    Mengambil data dari Google Sheets dengan caching 10 menit.
    Membuat koneksi gspread baru di dalam cache untuk mencegah error token terputus/stale.
    """
    try:
        gc = gspread.service_account_from_dict(gcp_dict)
        sheet = gc.open_by_key(sheet_key).get_worksheet(0)
        records = sheet.get_all_records()
        if not records:
            # Fallback jika header/baris kosong atau terkelola via get_all_values
            data = sheet.get_all_values()
            if data and len(data) > 1:
                return pd.DataFrame(data[1:], columns=data[0])
            return pd.DataFrame()
        return pd.DataFrame(records)
    except Exception as e:
        raise RuntimeError(f"Gagal memuat data Google Sheets: {e}")

# ==========================================================
# === OTAK AI (GEMINI) ===
# ==========================================================
def get_ai_recommendation(item, kegunaan, pph, df_database, api_key):
    if df_database.empty:
        return "⚠️ Database COA kosong atau gagal dimuat. Tidak dapat memproses rekomendasi."

    # Ubah database menjadi string CSV agar bisa dibaca AI
    db_string = df_database.to_csv(index=False)
    
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
        client = genai.Client(api_key=api_key)
        # Gunakan nama model yang valid pada SDK Google GenAI (gemini-2.5-flash)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=gemini_prompt
        )
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
        st.error("❌ API key Gemini (GEMINI_API_KEY) tidak ditemukan di secrets.toml atau environment variables.")
        st.stop()

    if "gcp_service_account" not in st.secrets:
        st.error("❌ Kredensial 'gcp_service_account' tidak ditemukan di secrets.toml.")
        st.stop()

    try:
        gcp_dict = dict(st.secrets["gcp_service_account"])
        # Perbaiki newline pada private_key jika tersimpan sebagai string "\\n" di secrets.toml
        if "private_key" in gcp_dict and isinstance(gcp_dict["private_key"], str):
            gcp_dict["private_key"] = gcp_dict["private_key"].replace("\\n", "\n")
    except Exception as e:
        st.error(f"❌ Gagal memproses format kredensial GCP: {e}")
        st.stop()

    SHEET_KEY = st.secrets.get("SHEET_KEY")
    if not SHEET_KEY:
        st.error("❌ SHEET_KEY tidak ditemukan di secrets.toml.")
        st.stop()

    # --- 2. AMBIL DATABASE ---
    try:
        df_coa = get_database_df(gcp_dict, SHEET_KEY)
    except Exception as e:
        st.error(f"❌ {e}")
        st.stop()

    # --- 3. TAMPILAN UI ---
    st.title("🤖 Asisten Kasir Petty Cash")
    st.write("Saya terhubung dengan 'Data Base COA' dan siap membantu Anda.")
    st.divider()
    
    st.header("🔍 Cari Rekomendasi Akun COA")
    st.write("Masukkan detail pengeluaran untuk menemukan COA yang tepat.")

    with st.form(key="search_form"):
        col1, col2 = st.columns(2)
        with col1:
            item_dibeli = st.text_input("Item yg dibeli:", placeholder="Contoh: Aqua Galon")
        with col2:
            digunakan_untuk = st.text_input("Digunakan Untuk:", placeholder="Contoh: Minum karyawan")
        
        pph_faktur = st.radio("Potong PPh / Dapat Faktur Pajak?", ("No", "Yes"), index=0, horizontal=True)
        submitted = st.form_submit_button("Cari Rekomendasi COA")

    if submitted:
        if not item_dibeli or not digunakan_untuk:
            st.warning("Mohon isi kedua kolom (Item & Digunakan Untuk).")
        else:
            with st.spinner("Menganalisa dan mencari COA yang tepat..."):
                hasil_ai = get_ai_recommendation(item_dibeli, digunakan_untuk, pph_faktur, df_coa, API_KEY)
                
                st.subheader("Hasil Rekomendasi:")
                # Langsung tampilkan via st.markdown agar format teks rapi & link URL otomatis clickable
                st.markdown(hasil_ai)

# ==========================================================
# === TITIK MASUK APLIKASI ===
# ==========================================================
if __name__ == "__main__":
    login_form()