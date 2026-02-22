import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
import google.generativeai as genai

# ==========================================================
# === FUNGSI LOGIN (TIDAK BERUBAH) ===
# ==========================================================
def login_form():
    """
    Menampilkan form login dan mengautentikasi pengguna.
    Menggunakan st.secrets untuk kredensial yang aman.
    """
    
    # Inisialisasi session state untuk status login
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    # Jika pengguna sudah login, langsung jalankan aplikasi utama
    if st.session_state.authenticated:
        run_coa_bot() # <-- Menjalankan aplikasi COA Anda
    
    # Jika pengguna belum login, tampilkan form
    else:
        st.set_page_config(page_title="Login - COA Bot", layout="centered")
        st.title("🔒 Silakan Login")
        st.write("Masukkan kredensial untuk mengakses Asisten Kasir Petty Cash.")

        with st.form("login_form"):
            username = st.text_input("Username", placeholder="Username Anda")
            password = st.text_input("Password", type="password", placeholder="Password Anda")
            
            submitted = st.form_submit_button("Login") 

            if submitted:
                # Cek kredensial dari Streamlit Secrets
                try:
                    correct_user = st.secrets["app_credentials"]["APP_USER"]
                    correct_pass = st.secrets["app_credentials"]["APP_PASS"]
                except KeyError:
                    st.error("Kredensial [app_credentials] belum di-setting di secrets.toml")
                    return
                except Exception as e:
                    st.error(f"Error saat membaca secrets: {e}")
                    return

                # Verifikasi login
                if username == correct_user and password == correct_pass:
                    st.session_state.authenticated = True
                    st.success("Login berhasil! Memuat aplikasi...")
                    st.rerun() # Muat ulang halaman (penting!)
                else:
                    st.error("Username atau Password salah.")

# ==========================================================
# === APLIKASI CHATBOT UTAMA (KODE LAMA ANDA) ===
# ==========================================================
def run_coa_bot():
    """
    Ini adalah seluruh kode aplikasi Petty Cash Anda yang lama,
    sekarang dibungkus dalam satu fungsi.
    """
    
    # --- KONFIGURASI KONEKSI GOOGLE SHEETS ---
    @st.cache_data(ttl=600) # Cache data selama 10 menit
    def load_database_coa():
        """Memuat data COA dari Google Sheets menggunakan service account."""
        
        try:
            # Ambil kredensial dari Streamlit Secrets
            creds_dict = dict(st.secrets["google_credentials"])
            
            # ==================================================
            # === PERUBAHAN: MENYAMAKAN DENGAN PROMO BOT ===
            # ==================================================
            gc = gspread.service_account_from_dict(creds_dict)
            
            # Panggil Sheet Key dari secrets
            sheet_key = st.secrets["SHEET_KEY"]
            sh = gc.open_by_key(sheet_key) 
            # ==================================================
            
            # Ambil worksheet pertama (index 0)
            worksheet = sh.get_worksheet(0) 
            
            data = worksheet.get_all_records()
            df = pd.DataFrame(data)
            
            return df

        except gspread.exceptions.SpreadsheetNotFound:
            st.error("Error: Spreadsheet tidak ditemukan.")
            st.error("Pastikan URL Sheet benar dan akun service (bot-pembaca-sheet@...) sudah di-invite ke Sheet.")
            return pd.DataFrame()
        except gspread.exceptions.APIError as e:
            st.error(f"Error Google API: {e}")
            st.error("Pastikan 'Google Sheets API' sudah di-enable di Google Cloud Project Anda.")
            return pd.DataFrame()
        except Exception as e:
            st.error(f"Gagal memuat 'Data Base COA':")
            st.exception(e) # Menampilkan detail error
            return pd.DataFrame()

    # --- KONFIGURASI GOOGLE AI (CHATBOT) ---
    try:
        # Ambil API Key Gemini dari Streamlit Secrets
        GOOGLE_AI_API_KEY = st.secrets["google_ai"]["api_key"]
        genai.configure(api_key=GOOGLE_AI_API_KEY)
        
        # Inisialisasi model
        model = genai.GenerativeModel('models/gemini-flash-latest')
        
        # --- TAMPILAN APLIKASI STREAMLIT ---
        # (Dipindahkan dari atas ke sini)
        st.set_page_config(layout="wide") 
        st.title("🤖 Asisten Kasir Petty Cash")
        st.write("Saya terhubung dengan 'Data Base COA' dan siap membantu Anda.")
        
        # Muat data COA (sekarang berjalan 'diam-diam')
        df_coa = load_database_coa()
        
        # Hanya lanjutkan jika data berhasil dimuat
        if not df_coa.empty:
            
            # Ubah dataframe menjadi string CSV untuk konteks prompt
            # (Ini tetap diperlukan agar AI bisa bekerja)
            data_konteks_coa = df_coa.to_csv(index=False)
            
            st.divider()
            st.header("🔍 Cari Rekomendasi Akun COA")
            st.write("Masukkan detail pengeluaran untuk menemukan COA yang tepat.")

            with st.form(key="search_form"):
                col1, col2 = st.columns(2)
                
                with col1:
                    item_dibeli = st.text_input(
                        "Item yg dibeli:", 
                        placeholder="Contoh: Aqua Galon"
                    )
                
                with col2:
                    digunakan_untuk = st.text_input(
                        "Digunakan Untuk:", 
                        placeholder="Contoh: Minum karyawan"
                    )
                
                # ==========================================================
                # === TAMBAHAN INPUT PPH ===
                # ==========================================================
                pph_faktur = st.radio(
                    "Potong PPh / Dapat Faktur Pajak?",
                    ("No", "Yes"), 
                    index=0, 
                    horizontal=True
                )
                # ==========================================================
                
                submitted = st.form_submit_button("Cari Rekomendasi COA")

            if submitted:
                if not item_dibeli or not digunakan_untuk:
                    st.warning("Mohon isi kedua kolom (Item & Digunakan Untuk).")
                else:
                    # ==========================================================
                    # === PROMPT SISTEM V7 (TIDAK BERUBAH) ===
                    # ==========================================================
                    prompt_sistem = f"""
                    # PERINTAH INTERNAL (JANGAN DITAMPILKAN KE USER)
                    Anda adalah Asisten Kasir yang sangat teliti dan cerdas.
                    Tugas Anda adalah bertindak sebagai sistem pencari (lookup system) yang akurat.
                    Gunakan HANYA 'Data Base COA' sebagai sumber kebenaran.
                    
                    --- DATA COA (format CSV) ---
                    {data_konteks_coa}
                    --- AKHIR DATA COA ---
                    
                    Input dari Kasir:
                    1.  Item yg dibeli: "{item_dibeli}"
                    2.  Digunakan Untuk: "{digunakan_untuk}"
                    3.  Potong PPh / Faktur Pajak: "{pph_faktur}"
                    
                    # PROSES BERPIKIR INTERNAL (JANGAN DITAMPILKAN KE USER)
                    1.  **Tahap 1 (Pencocokan Fleksibel):** Gunakan pengetahuan umum DAN data COA untuk menemukan **satu baris** yang paling relevan berdasarkan 'Item yg dibeli' dan 'Digunakan Untuk'.
                        * Contoh Fleksibel: Jika user input "batagor", ini harus cocok dengan baris "Makan lainnya".
                        * Contoh Fleksibel: Jika user input "pulpen", ini harus cocok dengan baris "Supplies Alat Tulis Kantor".
                        
                    2.  **Tahap 2 (Validasi KETAT untuk ATK):** SETELAH kamu menemukan baris yang paling relevan (dari Tahap 1), kamu WAJIB melakukan validasi:
                        * **JIKA** baris yang cocok adalah "Supplies Alat Tulis Kantor" (Akun 60018020):
                            * Kamu HARUS melihat isi dari sel `ITEM_YANG_DIBELI` untuk baris itu. Itu adalah DAFTAR RESMI ATK.
                            * Periksa apakah `Item yg dibeli` ("{item_dibeli}") ada di dalam daftar resmi di sel tersebut.
                            * Jika **TIDAK ADA** (contoh: "pulpen" tidak ada di daftar itu), maka batalkan pencarian dan anggap **TIDAK DITEMUKAN**.
                        * **JIKA** baris yang cocok adalah "Makan lainnya" (atau baris lain yang BUKAN ATK):
                            * Pencocokan fleksibel (dari Tahap 1) diterima. "Batagor" boleh cocok.

                    3.  **Tahap 3 (Validasi PPh / Faktur Pajak):**
                        * SETELAH menemukan baris yang cocok (dan lolos Tahap 2), siapkan variabel-variabel ini dari baris yang cocok:
                            * `VAR_COA` = [Isi kolom BUSINESS_TRANSACTION_(COA)]
                            * `VAR_GL` = [Isi kolom NO_GIL_ACCOUNT]
                            * `VAR_CATATAN` = [Isi kolom REMARK]
                            * `VAR_APPROVAL` = [Isi kolom APPROVAL]
                            * `VAR_BUDGET` = [Isi kolom BUDGET]
                            * `VAR_PROFIT` = [Isi kolom PROFIT_CENTER]
                            * `VAR_COST` = [Isi kolom COST_CENTER]

                        * **JIKA** input 'Potong PPh / Faktur Pajak' adalah "Yes":
                            * Ganti `VAR_COA` = "Pembayaran Pemasok"
                            * Ganti `VAR_GL` = "N/A"
                            * **Tambahkan catatan PPh ini:** `VAR_CATATAN` = "- NPWP PT / Badan potong PPh 2% dari DPP\n- NPWP Perorangan potong PPh 2.5% dari DPP\n" + `VAR_CATATAN` (tambahkan catatan PPh di awal, lalu ikuti dengan catatan asli).
                        
                        * **JIKA** inputnya adalah "No":
                            * Biarkan semua variabel apa adanya.

                    4.  **Tahap 4 (Filter 'Catatan' dan 'Approval'):**
                        * Sekarang, ambil `VAR_CATATAN` dan `VAR_APPROVAL` (yang mungkin sudah diubah di Tahap 3).
                        * Kamu HARUS memfilter isi variabel-variabel ini dan HANYA menampilkan teks yang relevan dengan input "Digunakan Untuk:" ("{digunakan_untuk}").
                        * **PENTING:** Jika PPh="Yes", jangan hapus catatan PPh ("- NPWP PT / Badan...") yang baru ditambahkan. Kamu hanya boleh memfilter bagian `VAR_CATATAN` yang berasal dari database asli (GSheet).
                        * **Contoh:** Jika "{digunakan_untuk}" adalah "snack coffe morning", HAPUS aturan "Makan Staff" dari `VAR_CATATAN` dan `VAR_APPROVAL`.
                    
                    # PERATURAN OUTPUT FINAL (WAJIB DIPATUHI)
                    Setelah kamu menyelesaikan semua PROSES BERPIKIR INTERNAL (Tahap 1-4):
                    -   **JANGAN** tampilkan alur berpikirmu.
                    -   **JANGAN** tampilkan "Tahap 1", "Tahap 2", "Variabel", atau "Hasil Akhir:"
                    -   Langsung berikan jawaban final sebagai plain text.

                    **Output JIKA DITEMUKAN:**
                    (HANYA teks di bawah ini, isi dengan variabel final)
                    Rekomendi COA: [Isi `VAR_COA`]
                    No. G/L Account: [Isi `VAR_GL`]
                    Catatan: [Isi `VAR_CATATAN` setelah difilter]
                    Approval: [Isi `VAR_APPROVAL` setelah difilter]
                    Budget: [Isi `VAR_BUDGET`]
                    Profit Center: [Isi `VAR_PROFIT`]
                    Cost Center: [Isi `VAR_COST`]

                    **Output JIKA GAGAL:**
                    (HANYA teks di bawah ini)
                    Saya tidak dapat menemukan akun yang cocok untuk item tersebut.
                    """
                    # ==========================================================
                    
                    with st.spinner("Menganalisa dan mencari COA yang tepat..."):
                        try:
                            response = model.generate_content(prompt_sistem)
                            st.subheader("Hasil Rekomendasi:")
                            
                            # ==================================================
                            # === PERUBAHAN DI SINI (AGAR LINK BISA DI-KLIK) ===
                            # ==================================================
                            # Kita proses jawaban baris per baris.
                            # Jika ada "http" di baris itu, kita pakai st.markdown()
                            # agar bisa diklik.
                            # Jika tidak ada, kita pakai st.text() agar format PPh aman.
                            
                            hasil_teks = response.text
                            
                            for baris in hasil_teks.split('\n'):
                                if "http://" in baris or "https://" in baris:
                                    st.markdown(baris)
                                else:
                                    # Tampilkan sebagai teks biasa
                                    st.text(baris)
                            # ==================================================
                            
                        except Exception as e:
                            st.error("Terjadi error saat menghubungi Google AI:")
                            st.exception(e)
        
        # Menambahkan 'else' untuk kasus jika data GAGAL dimuat
        else:
            st.error("Gagal memuat data base COA. Aplikasi tidak dapat dijalankan.")
            st.info("Silakan hubungi administrator atau cek koneksi/izin Google Sheet.")


    except KeyError as e:
        # Penyesuaian pesan error agar lebih spesifik
        if 'app_credentials' in str(e):
             st.error(f"Error: Kunci (key) '{e}' tidak ditemukan di file secrets.toml")
             st.info("Pastikan Anda sudah menambahkan blok [app_credentials] di file secrets.toml lokal Anda.")
        else:
            st.error(f"Error: Kunci (key) '{e}' tidak ditemukan di file secrets.toml")
            st.info("Pastikan file .streamlit/secrets.toml Anda memiliki struktur [google_credentials] dan [google_ai] yang benar.")
    except Exception as e:
        st.error("Terjadi error fatal pada konfigurasi aplikasi:")
        st.exception(e)

# ==========================================================
# === TITIK MASUK APLIKASI (BARU) ===
# ==========================================================

# Panggil fungsi login_form() sebagai hal pertama.
# Fungsi ini akan memutuskan apakah akan menampilkan form login
# atau menjalankan run_coa_bot().
login_form()