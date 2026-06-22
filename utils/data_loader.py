# utils/data_loader.py
import pandas as pd
import streamlit as st

def load_dpc_file(file, columns_def, numeric_cols=None):
    try:
        df = pd.read_csv(file, sep='\t', header=None, encoding='cp932', names=columns_def, dtype=str)
        for col in df.columns:
            df[col] = df[col].astype(str).str.strip()
        if numeric_cols:
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
        return df
    except Exception as e:
        st.error(f"DPCファイルの読み込み中にエラーが発生しました: {e}")
        return None

def load_master_file(file, master_name):
    try:
        df = pd.read_csv(
            file, sep=',', header=None, encoding='cp932', 
            usecols=[2, 11], names=["レセ電コード", "償還価格"], dtype={"レセ電コード": str}
        )
        df["レセ電コード"] = df["レセ電コード"].astype(str).str.strip()
        df["償還価格"] = pd.to_numeric(df["償還価格"], errors='coerce')
        return df
    except Exception as e:
        st.error(f"{master_name}の読み込み中にエラーが発生しました: {e}")
        return None

def load_allocation_base_master(file):
    try:
        df = pd.read_csv(
            file, sep='\t', header=None, encoding='cp932',
            usecols=[6, 8, 10], names=["部署コード", "部門コード", "レセ電コード"],
            dtype=str
        )
    except UnicodeDecodeError:
        file.seek(0)
        try:
            df = pd.read_csv(
                file, sep='\t', header=None, encoding='utf_8_sig',
                usecols=[6, 8, 10], names=["部署コード", "部門コード", "レセ電コード"],
                dtype=str
            )
        except Exception as e:
            st.error(f"配賦基準マスタの読み込み中に文字コードエラーが発生しました: {e}")
            return None
    except Exception as e:
        st.error(f"配賦基準マスタの読み込み中に予期せぬエラーが発生しました: {e}")
        return None

    df["部署コード"] = df["部署コード"].astype(str).str.strip()
    df["部門コード"] = df["部門コード"].astype(str).str.strip()
    df["レセ電コード"] = df["レセ電コード"].astype(str).str.strip()
    return df

def load_department_cost_master(file, max_dept_len=2):
    try:
        df = pd.read_csv(file, sep=',', encoding='cp932', dtype=str)
    except UnicodeDecodeError:
        file.seek(0)
        try:
            df = pd.read_csv(file, sep=',', encoding='utf_8_sig', dtype=str)
        except Exception as e:
            st.error(f"部署別費用マスタの読み込み中に文字コードエラーが発生しました: {e}")
            return None
    except Exception as e:
        st.error(f"部署別費用マスタの読み込み中に予期せぬエラーが発生しました: {e}")
        return None

    try:
        df["部門区分"] = df["部門区分"].astype(str).str.strip()
        df["部署コード"] = df["部署コード"].astype(str).str.strip()
        df["部署名"] = df["部署名"].astype(str).str.strip().fillna("")
        
        is_shinjyoka = df["部門区分"] == "診療科"
        df.loc[is_shinjyoka, "部署コード"] = df.loc[is_shinjyoka, "部署コード"].apply(lambda x: x.zfill(max_dept_len) if x.isdigit() else x)
        
        df["収益"] = pd.to_numeric(df["収益"], errors='coerce').fillna(0)
        df["費用"] = pd.to_numeric(df["費用"], errors='coerce').fillna(0)
        return df
    except Exception as e:
        st.error(f"部署別費用マスタのデータ加工中にエラーが発生しました: {e}")
        return None