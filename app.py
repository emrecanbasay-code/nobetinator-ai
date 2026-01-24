# TAB 2: KOTALAR - DÜZELTİLMİŞ VERSİYON
with t2:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    
    total_need_24 = sum(st.session_state.daily_needs_24h.get(d, 1) for d in range(1, num_days+1))
    total_need_16 = sum(st.session_state.daily_needs_16h.get(d, 1) for d in range(1, num_days+1))
    current_dist_24 = sum(st.session_state.quotas_24h.get(d, 0) for d in st.session_state.doctors)
    current_dist_16 = sum(st.session_state.quotas_16h.get(d, 0) for d in st.session_state.doctors)
    
    col_q1, col_q2 = st.columns(2)
    col_q1.metric("24h İhtiyaç / Dağıtılan", f"{total_need_24} / {current_dist_24}", delta=f"{current_dist_24 - total_need_24}", delta_color="off")
    col_q2.metric("16h İhtiyaç / Dağıtılan", f"{total_need_16} / {current_dist_16}", delta=f"{current_dist_16 - total_need_16}", delta_color="off")
    
    st.markdown("---")
    
    with st.expander("📤 Kota Toplu Yükleme (Excel)", expanded=True):
        col_dl, col_up = st.columns([1, 2])
        with col_dl:
            sample_data = [{"Dr": d, "Max 24h": 0, "Max 16h": 0} for d in st.session_state.doctors]
            sample_df = pd.DataFrame(sample_data)
            
            buf_quota = io.BytesIO()
            with pd.ExcelWriter(buf_quota, engine='xlsxwriter') as writer:
                sample_df.to_excel(writer, index=False, sheet_name='Kotalar')
                
            st.download_button(
                label="📥 Excel Şablonu İndir", 
                data=buf_quota.getvalue(), 
                file_name="kota_sablonu.xlsx", 
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                use_container_width=True
            )
        
        with col_up:
            with st.form("quota_upload_form", clear_on_submit=False):
                uploaded_quotas = st.file_uploader("Excel Dosyası", type=["xlsx"], label_visibility="collapsed")
                submit_quota = st.form_submit_button("📂 Kotaları İşle", type="primary", use_container_width=True)
                
                if submit_quota and uploaded_quotas:
                    try:
                        # Excel'i oku
                        df_up = pd.read_excel(uploaded_quotas, engine='openpyxl')
                        
                        # Debug: Gelen sütunları göster
                        st.info(f"📋 Excel'deki sütunlar: {list(df_up.columns)}")
                        
                        # Sütun isimlerini normalize et
                        df_up.columns = [str(c).strip() for c in df_up.columns]
                        
                        # Tam eşleşme kontrolü
                        required = ["Dr", "Max 24h", "Max 16h"]
                        
                        if all(c in df_up.columns for c in required):
                            count = 0
                            updated_list = []
                            not_found = []
                            
                            for idx, row in df_up.iterrows():
                                dname = str(row["Dr"]).strip()
                                
                                if dname in st.session_state.doctors:
                                    try:
                                        val_24 = int(float(row["Max 24h"]))
                                        val_16 = int(float(row["Max 16h"]))
                                        
                                        # Session state'e yaz
                                        st.session_state.quotas_24h[dname] = val_24
                                        st.session_state.quotas_16h[dname] = val_16
                                        
                                        updated_list.append(f"{dname}: 24h={val_24}, 16h={val_16}")
                                        count += 1
                                    except (ValueError, TypeError) as e:
                                        st.warning(f"⚠️ {dname} için hatalı değer: {e}")
                                else:
                                    not_found.append(dname)
                            
                            # Sonuçları göster
                            if count > 0:
                                st.success(f"✅ {count} doktor güncellendi!")
                                with st.expander("📋 Detaylar"):
                                    for u in updated_list:
                                        st.write(f"✓ {u}")
                                    if not_found:
                                        st.write(f"⚠️ Bulunamadı: {', '.join(not_found)}")
                                
                                # Rerun ZORUNLU
                                st.session_state.editor_key += 1
                                st.rerun()
                            else:
                                st.error(f"❌ Hiçbir isim eşleşmedi!")
                                st.write("Excel'deki isimler:", list(df_up["Dr"]))
                                st.write("Sistemdeki isimler:", st.session_state.doctors)
                        else:
                            st.error(f"❌ Sütunlar eksik!")
                            st.write(f"Aranan: {required}")
                            st.write(f"Bulunan: {list(df_up.columns)}")
                            
                    except Exception as e:
                        st.error(f"❌ Hata: {str(e)}")
                        import traceback
                        st.code(traceback.format_exc())

    # Manuel Tablo Düzenleme
    st.markdown("### ✏️ Manuel Düzenleme")
    q_data = [{"Dr": d, "Max 24h": st.session_state.quotas_24h.get(d, 0), "Max 16h": st.session_state.quotas_16h.get(d, 0)} for d in st.session_state.doctors]
    
    with st.form("quotas_manual"):
        qdf = st.data_editor(
            pd.DataFrame(q_data), 
            key=f"quota_ed_{st.session_state.editor_key}", 
            use_container_width=True, 
            hide_index=True, 
            column_config={
                "Dr": st.column_config.TextColumn(disabled=True),
                "Max 24h": st.column_config.NumberColumn(min_value=0, max_value=31, step=1),
                "Max 16h": st.column_config.NumberColumn(min_value=0, max_value=31, step=1)
            }
        )
        
        if st.form_submit_button("💾 Tablodan Kaydet", use_container_width=True):
            changes_made = False
            for i, r in qdf.iterrows():
                old_24 = st.session_state.quotas_24h.get(r["Dr"], 0)
                old_16 = st.session_state.quotas_16h.get(r["Dr"], 0)
                new_24 = int(r["Max 24h"])
                new_16 = int(r["Max 16h"])
                
                if old_24 != new_24 or old_16 != new_16:
                    st.session_state.quotas_24h[r["Dr"]] = new_24
                    st.session_state.quotas_16h[r["Dr"]] = new_16
                    changes_made = True
            
            if changes_made:
                st.success("✅ Kotalar kaydedildi!")
                st.rerun()
            else:
                st.info("ℹ️ Değişiklik yapılmadı.")
                
    st.markdown('</div>', unsafe_allow_html=True)
