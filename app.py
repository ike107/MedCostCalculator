# app.py
import pandas as pd
import streamlit as st

from config import D_COLUMNS, E_COLUMNS, F_COLUMNS
from utils.data_loader import (
    load_dpc_file, load_master_file, load_allocation_base_master, load_department_cost_master
)
from utils.cost_allocator import (
    merge_and_calculate_patient_revenue, calculate_direct_costs,
    flag_patient_count_target, generate_department_template, allocate_indirect_costs
)

@st.cache_data
def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf_8_sig')

def main():
    st.title("DPCデータ 損益計算（PL）ダッシュボード")
    
    # ─── 画面最上部で「作業用」と「結果確認用」にタブを大きく2分割 ───
    main_tab1, main_tab2 = st.tabs(["📥 データ取込・マスタ設定（作業用）", "📊 分析結果の確認"])
    
    # セッション状態の初期化（タブを跨いで計算データを保持するため）
    if "def_df" not in st.session_state:
        st.session_state.def_df = None
    if "dfs" not in st.session_state:
        st.session_state.dfs = {
            'D': None, 'E': None, 'F': None,
            '配賦基準マスタ': None, '医薬品マスタ': None, '特定器材マスタ': None,
            '部署別費用マスタ': None
        }

    # ==========================================
    # 【第1タブ】📥 データ取込・マスタ設定（作業用）
    # ==========================================
    with main_tab1:
        st.header("1. データのアップロード（ファーストステップ）")
        st.write("DPCデータファイルおよび必須マスタファイルをすべて選択してください。")
        
        # タブを分けずに1つの画面にアップローダーを並べる
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            st.subheader("DPCデータ（厚生労働省標準様式）")
            d_file = st.file_uploader("Dファイルをアップロードしてください（必須）", type=["txt", "tsv"])
            e_file = st.file_uploader("Eファイルをアップロードしてください（必須）", type=["txt", "tsv"])
            f_file = st.file_uploader("Fファイルをアップロードしてください（必須）", type=["txt", "tsv"])
        
        with col_f2:
            st.subheader("配賦基準および出来高単価マスタ")
            allocation_base_file = st.file_uploader("配賦基準マスタをアップロードしてください (.tab)", type=["tab", "txt"])
            med_file = st.file_uploader("医薬品マスタをアップロードしてください (.csv)", type=["csv"])
            mat_file = st.file_uploader("特定器材マスタをアップロードしてください (.csv)", type=["csv"])

        # ─── 初期データの個別の読込処理（選択された瞬間にその都度処理） ───
        if d_file and st.session_state.dfs['D'] is None:
            st.session_state.dfs['D'] = load_dpc_file(d_file, D_COLUMNS, numeric_cols=["行為点数", "行為回数", "医療機関関係数"])
        if st.session_state.dfs['D'] is not None:
            st.sidebar.success("✅ Dファイル 読込成功")

        if e_file and st.session_state.dfs['E'] is None:
            st.session_state.dfs['E'] = load_dpc_file(e_file, E_COLUMNS, numeric_cols=["行為点数", "行為回数"])
        if st.session_state.dfs['E'] is not None:
            st.sidebar.success("✅ Eファイル 読込成功")

        if f_file and st.session_state.dfs['F'] is None:
            st.session_state.dfs['F'] = load_dpc_file(f_file, F_COLUMNS, numeric_cols=["行為明細点数", "行為明細出来高点数", "行為明細出来高金額", "行為明細薬剤料", "行為明細材料料"])
        if st.session_state.dfs['F'] is not None:
            st.sidebar.success("✅ Fファイル 読込成功")

        if allocation_base_file and st.session_state.dfs['配賦基準マスタ'] is None:
            st.session_state.dfs['配賦基準マスタ'] = load_allocation_base_master(allocation_base_file)
        if st.session_state.dfs['配賦基準マスタ'] is not None:
            st.sidebar.success("✅ 配賦基準マスタ 読込成功")

        if med_file and st.session_state.dfs['医薬品マスタ'] is None:
            st.session_state.dfs['医薬品マスタ'] = load_master_file(med_file, "医薬品マスタ")
        if st.session_state.dfs['医薬品マスタ'] is not None:
            st.sidebar.success("✅ 医薬品マスタ 読込成功")

        if mat_file and st.session_state.dfs['特定器材マスタ'] is None:
            st.session_state.dfs['特定器材マスタ'] = load_master_file(mat_file, "特定器材マスタ")
        if st.session_state.dfs['特定器材マスタ'] is not None:
            st.sidebar.success("✅ 特定器材マスタ 読込成功")

        # ─── 必須マスタがすべて揃った後の統合計算フェーズ ───
        required_keys = ['D', 'E', 'F', '配賦基準マスタ', '医薬品マスタ', '特定器材マスタ']
        if all(st.session_state.dfs[key] is not None for key in required_keys):
            if st.session_state.def_df is None:
                st.sidebar.info("✨ 初期必須ファイルがすべて揃いました")
                
                # 初期計算とテンプレート用ベースデータの作成
                calc_df = merge_and_calculate_patient_revenue(st.session_state.dfs)
                calc_df = calculate_direct_costs(calc_df, st.session_state.dfs)
                calc_df = flag_patient_count_target(calc_df, st.session_state.dfs)
                
                st.session_state.def_df = calc_df

        # ─── ② 部署別費用入力用テンプレートの生成 ───
        if st.session_state.def_df is not None:
            st.write("---")
            st.header("2. 部署別費用入力用テンプレートの生成")
            
            # テンプレートのDataFrameを生成
            template_df = generate_department_template(st.session_state.def_df)
            
            # 【修正】DataFrameオブジェクトを、st.download_buttonが受け取れるCSVバイナリデータに変換
            template_csv = template_df.to_csv(index=False).encode('utf_8_sig')
            
            st.download_button(
                label="📥 部署別費用入力用テンプレート(CSV)をダウンロード",
                data=template_csv,
                file_name="部署別費用マスタ_テンプレート.csv",
                mime="text/csv",
                key="download-template-csv"
            )

            # ─── ③ 記入済み部署別費用マスタの取り込みと最終配賦 ───
            st.write("---")
            st.header("3. 記入済み部署別費用マスタの取り込みと最終配賦")
            filled_dept_cost_file = st.file_uploader("記入済みの「部署別費用マスタ」をアップロードしてください (.csv)", type=["csv"])
            
            if filled_dept_cost_file:
                if "診療科区分" in st.session_state.def_df.columns:
                    max_len = st.session_state.def_df["診療科区分"].dropna().astype(str).str.strip().str.len().max()
                    if pd.isna(max_len) or max_len == 0:
                        max_len = 2
                else:
                    max_len = 2
                
                st.session_state.dfs['部署別費用マスタ'] = load_department_cost_master(filled_dept_cost_file, max_dept_len=int(max_len))
                
                if st.session_state.dfs['部署別費用マスタ'] is not None:
                    st.sidebar.success("✅ 記入済み部署別費用マスタ 読込成功")
                    
                    # 配賦計算を実行してセッションに格納
                    st.session_state.def_df = allocate_indirect_costs(st.session_state.def_df, st.session_state.dfs)
                    st.success("🎉 すべての間接費用配賦が完了しました！上の「分析結果の確認」タブに移動して結果を確認してください。")

            # ─── ⑥ 【最終データの検証・出力】（作業用タブの最下部に配置） ───
            # 配賦間接費カラムが生成されている（配賦完了している）場合のみダウンロードボタンを有効化
            if "配賦間接費" in st.session_state.def_df.columns:
                st.write("---")
                st.header("6. 最終データの検証・出力")
                with st.spinner("ダウンロード用ファイルの準備中..."):
                    csv_data = convert_df_to_csv(st.session_state.def_df)
                
                st.download_button(
                    label="📥 全計算済のDEF結合データをCSVでダウンロード",
                    data=csv_data,
                    file_name="def_merged_full_calculated.csv",
                    mime="text/csv",
                    key="download-def-csv-final"
                )

    # ==========================================
    # 【第2タブ】📊 分析結果の確認
    # ==========================================
    with main_tab2:
        # まだ費用配賦まで終わっていない場合のガード
        if st.session_state.def_df is None or "配賦間接費" not in st.session_state.def_df.columns:
            st.info("💡 データのアップロードと、手順3の「記入済み部署別費用マスタの取り込み」を完了させると、ここに分析結果が表示されます。")
        else:
            # ─── ④ 【損益計算（PL）集計結果】 ───
            st.header("4. 損益計算（PL）集計結果")
            
            grand_total_revenue = st.session_state.def_df["収益"].sum()
            grand_total_direct_cost = st.session_state.def_df["直接原価"].sum()
            grand_total_indirect_cost = st.session_state.def_df["配賦間接費"].sum()
            target_record_count = st.session_state.def_df["延べ患者カウント対象フラグ"].sum()
            
            # 【修正】st.columnsを撤廃し、縦に1行ずつ並べることで数値の見切れを完全に防ぎます
            st.metric(label="💰 収益総額", value=f"{grand_total_revenue:,} 円")
            st.metric(label="📦 直接原価合計", value=f"{grand_total_direct_cost:,} 円")
            st.metric(label="🏛️ 配賦間接費合計", value=f"{grand_total_indirect_cost:,} 円")
            st.metric(label="📋 延べ患者カウント総数", value=f"{target_record_count:,} 日")
                                                
            st.markdown("##### 🔍 計算済データプレビュー（先頭5件）")
            preview_cols = [
                "データ識別番号", "入院年月日", "診療行為名称", "レセ電コード", 
                "延べ患者カウント対象フラグ", "収益", "明細直接原価", "直接原価", "配賦間接費"
            ]
            st.dataframe(st.session_state.def_df[[col for col in preview_cols if col in st.session_state.def_df.columns]].head())

            # ─── 📊 患者別収支ダッシュボード ───
            st.write("---")
            st.header("📊 患者別収支ダッシュボード")
            st.write("Fファイルの全明細行から、データ識別番号（患者）ごとに再集約した収支分析です。")
            
            # 患者（データ識別番号）単位で集計
            patient_summary = st.session_state.def_df.groupby("データ識別番号").agg({
                "収益": "sum",
                "直接原価": "sum",
                "配賦間接費": "sum"
            }).reset_index()
            
            # 患者ごとの差引収支（利益・損失）を計算
            patient_summary["患者収支"] = (
                patient_summary["収益"] - 
                patient_summary["直接原価"] - 
                patient_summary["配賦間接費"]
            )
            
            # 丸めとソート（収支の大きい順：降順）
            patient_summary["患者収支"] = patient_summary["患者収支"].round().astype(int)
            patient_summary = patient_summary.sort_values(by="患者収支", ascending=False)
            
            display_cols = ["データ識別番号", "収益", "直接原価", "配賦間接費", "患者収支"]
            
            # 1. 収支トップ10（収支の高い順）
            st.markdown("#### 🏆 収支上位10名（利益貢献度の高い患者）")
            top_10 = patient_summary.head(10).copy()
            
            top_10_chart = top_10[["データ識別番号", "患者収支"]].set_index("データ識別番号")
            st.bar_chart(data=top_10_chart, color="#2ca02c")
            
            top_10_transposed = top_10[display_cols].set_index("データ識別番号").T
            st.dataframe(top_10_transposed.style.format("{:,.0f}"), width="stretch")
            
            st.write("---")
            
            # 2. 収支ワースト10（収支の低い順）
            st.markdown("#### ⚠️ 収支下位10名（コスト超過・損失の大きい患者）")
            bottom_10_sorted = patient_summary.tail(10).copy().sort_values(by="患者収支", ascending=True)
            
            bottom_10_chart = bottom_10_sorted[["データ識別番号", "患者収支"]].set_index("データ識別番号")
            st.bar_chart(data=bottom_10_chart, color="#d62728")
            
            bottom_10_transposed = bottom_10_sorted[display_cols].set_index("データ識別番号").T
            st.dataframe(bottom_10_transposed.style.format("{:,.0f}"), width="stretch")

            # ─── ⑤ 【配賦基準・単価の妥当性検証（監査用）】（確認用として一番下に配置） ───
            st.write("---")
            st.header("5. 配賦基準・単価の妥当性検証（監査用）")
            st.markdown("配賦ロジックが正しく機能しているか、各部署の単価・比率データで検証します。")

            audit_rows = []
            cost_master = st.session_state.dfs['部署別費用マスタ']

            # ① 診療科部門の検証
            dept1_costs = cost_master[cost_master["部門区分"] == "診療科"]
            for _, row in dept1_costs.iterrows():
                code = row["部署コード"]
                cost = row["費用"]
                name = row["部署名"]
                mask = (st.session_state.def_df["延べ患者カウント対象フラグ"] == True) & (st.session_state.def_df["診療科区分"] == code)
                denominator = mask.sum()
                unit_price = cost / denominator if denominator > 0 else 0
                audit_rows.append({
                    "部門区分": "① 診療科", "部署コード": code, "部署名": name, "総費用(円)": cost,
                    "分母（延べ患者数など）": f"{denominator:,} 日", "配賦単価・比率": f"{unit_price:,.1f} 円/日", "ステータス": "正常" if denominator > 0 or cost == 0 else "⚠️配賦対象(DPC)なし"
                })

            # ② 病棟部門の検証
            dept2_costs = cost_master[cost_master["部門区分"] == "病棟"]
            for _, row in dept2_costs.iterrows():
                code = row["部署コード"]
                cost = row["費用"]
                name = row["部署名"]
                actual_ward_code = code[1:] if code.startswith('B') else code
                mask = (st.session_state.def_df["延べ患者カウント対象フラグ"] == True) & (st.session_state.def_df["病棟コード"] == actual_ward_code)
                denominator = mask.sum()
                unit_price = cost / denominator if denominator > 0 else 0
                audit_rows.append({
                    "部門区分": "② 病棟", "部署コード": code, "部署名": name, "総費用(円)": cost,
                    "分母（延べ患者数など）": f"{denominator:,} 日", "配賦単価・比率": f"{unit_price:,.1f} 円/日", "ステータス": "正常" if denominator > 0 or cost == 0 else "⚠️配賦対象(DPC)なし"
                })

            # ③ 中央診療部門の検証
            dept3_costs = cost_master[cost_master["部門区分"] == "中央診療"]
            if len(dept3_costs) > 0 and st.session_state.dfs['配賦基準マスタ'] is not None:
                base_master = st.session_state.dfs['配賦基準マスタ']
                
                points = pd.to_numeric(st.session_state.def_df["行為明細点数"], errors='coerce').fillna(0.0)
                meds = pd.to_numeric(st.session_state.def_df["行為明細薬剤料"], errors='coerce').fillna(0.0)
                mats = pd.to_numeric(st.session_state.def_df["行為明細材料料"], errors='coerce').fillna(0.0)
                
                st.session_state.def_df["temp_base_amount"] = points + meds + mats
                
                q_div = st.session_state.def_df["円・点区分"].astype(str).str.strip()
                is_tensu = (q_div == "0") | (st.session_state.def_df["円・点区分"] == 0)
                st.session_state.def_df.loc[is_tensu, "temp_base_amount"] = st.session_state.def_df.loc[is_tensu, "temp_base_amount"] * 10
                
                base_master_sub = base_master[base_master["部署コード"] != "999"].drop_duplicates(subset=["レセ電コード", "部署コード"])
                target_lece_dict = {code: grp["レセ電コード"].unique() for code, grp in base_master_sub.groupby("部署コード")}
                
                for _, row in dept3_costs.iterrows():
                    code = row["部署コード"]
                    cost = row["費用"]
                    name = row["部署名"]
                    
                    target_leces = target_lece_dict.get(code, [])
                    mask = st.session_state.def_df["レセ電コード"].isin(target_leces)
                    denominator = st.session_state.def_df.loc[mask, "temp_base_amount"].sum() if mask.any() else 0
                    unit_price = cost / denominator if denominator > 0 else 0
                    
                    audit_rows.append({
                        "部門区分": "③ 中央診療", "部署コード": code, "部署名": name, "総費用(円)": cost,
                        "分母（延べ患者数など）": f"{denominator:,.0f} 円", "配賦単価・比率": f"{unit_price:,.3f} 円/円", "ステータス": "正常" if denominator > 0 or cost == 0 else "⚠️配賦対象(DPC)なし"
                    })
                st.session_state.def_df = st.session_state.def_df.drop(columns=["temp_base_amount"])

            # ④ その他部門の検証
            dept4_costs = cost_master[cost_master["部門区分"] == "その他"]
            total_other_cost = dept4_costs["費用"].sum()
            if total_other_cost > 0:
                mask = (st.session_state.def_df["延べ患者カウント対象フラグ"] == True)
                denominator = mask.sum()
                unit_price = total_other_cost / denominator if denominator > 0 else 0
                audit_rows.append({
                    "部門区分": "④ その他", "部署コード": "9999", "部署名": "共通管理費", "総費用(円)": total_other_cost,
                    "分母（延べ患者数など）": f"{denominator:,} 日", "配賦単価・比率": f"{unit_price:,.1f} 円/日", "ステータス": "正常" if denominator > 0 else "⚠️配賦対象(DPC)なし"
                })

            audit_df = pd.DataFrame(audit_rows)
            st.dataframe(top_10_transposed.style.format("{:,.0f}"), width="stretch")
            
            has_warning = audit_df["ステータス"].str.contains("⚠️").any()
            if has_warning:
                st.warning("💡 【注意】DPCデータ側に該当するコードの実績が存在しないため、費用を配賦できなかった部署があります。マスタの設定等をご確認ください。")
            else:
                st.success("✨ 【確認完了】すべての対象部署において、分母（実績データ）が存在し正常に配賦されています。")


if __name__ == "__main__":
    main()
