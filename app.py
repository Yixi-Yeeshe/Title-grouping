import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import os

# =========================
# 基本设置
# =========================

st.set_page_config(page_title="Title Coding App", layout="wide")

DATA_PATH = r"title 用于 app数据.csv"   # 你的csv上传到GitHub后的文件名
SPREADSHEET_ID = "你的Google Sheet ID"
WORKSHEET_NAME = "title_coding"        # 新worksheet名字，先在Google Sheet里手动建好

OPTIONS = {
    "A": "Obesity-focused",
    "B": "Obesity-relevant",
    "C": "Health-focused",
    "D": "Weight-loss-focused",
    "E": "Diet-focused",
    "F": "Food-focused",
    "G": "About weight-loss medicine",
    "H": "About body image",
    "I": "About other disease",
}

# =========================
# 读取CSV数据
# =========================

@st.cache_data
def load_data(path):
    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()

    if "New ID" not in df.columns:
        st.error("CSV里找不到 'New ID' 列。")
        st.stop()

    if "Title" not in df.columns:
        st.error("CSV里找不到 'Title' 列。")
        st.stop()

    df = df[["New ID", "Title"]].copy()
    df["New ID"] = df["New ID"].astype(str)
    df["Title"] = df["Title"].astype(str)

    return df


# =========================
# 连接Google Sheet
# =========================

@st.cache_resource
def connect_google_sheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes
    )

    client = gspread.authorize(creds)
    sheet = client.open_by_key(SPREADSHEET_ID)
    worksheet = sheet.worksheet(WORKSHEET_NAME)

    return worksheet


def load_existing_answers(worksheet):
    records = worksheet.get_all_records()

    if len(records) == 0:
        return pd.DataFrame(columns=[
            "coder", "New ID", "Title", "answer_code",
            "answer_label", "timestamp"
        ])

    df = pd.DataFrame(records)
    df.columns = df.columns.str.strip()

    if "New ID" in df.columns:
        df["New ID"] = df["New ID"].astype(str)

    return df


def save_answer(worksheet, coder, new_id, title, answer_code, answer_label):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    existing = worksheet.get_all_records()
    df_existing = pd.DataFrame(existing)

    if len(df_existing) > 0:
        df_existing.columns = df_existing.columns.str.strip()

        match_rows = df_existing[
            (df_existing["coder"].astype(str) == str(coder)) &
            (df_existing["New ID"].astype(str) == str(new_id))
        ]

        if len(match_rows) > 0:
            row_index = match_rows.index[0] + 2
            worksheet.update(
                f"A{row_index}:F{row_index}",
                [[coder, new_id, title, answer_code, answer_label, timestamp]]
            )
            return

    worksheet.append_row(
        [coder, new_id, title, answer_code, answer_label, timestamp],
        value_input_option="USER_ENTERED"
    )


# =========================
# App主体
# =========================

st.title("Title Coding App")

df = load_data(DATA_PATH)
worksheet = connect_google_sheet()

# 如果worksheet是空的，添加表头
if worksheet.row_count > 0:
    first_row = worksheet.row_values(1)
    if first_row == []:
        worksheet.append_row([
            "coder", "New ID", "Title", "answer_code",
            "answer_label", "timestamp"
        ])

coder = st.text_input("请输入你的名字 / coder name:")

if not coder:
    st.warning("请先输入 coder name。")
    st.stop()

existing_answers = load_existing_answers(worksheet)

coder_answers = existing_answers[
    existing_answers["coder"].astype(str) == str(coder)
] if len(existing_answers) > 0 and "coder" in existing_answers.columns else pd.DataFrame()

answered_ids = set(coder_answers["New ID"].astype(str)) if len(coder_answers) > 0 else set()

total_n = len(df)
answered_n = len(answered_ids)
remaining_n = total_n - answered_n

st.write(f"总标题数: {total_n}")
st.write(f"已完成: {answered_n}")
st.write(f"剩余: {remaining_n}")

progress = answered_n / total_n if total_n > 0 else 0
st.progress(progress)

# =========================
# 选择模式
# =========================

mode = st.radio(
    "请选择模式：",
    ["继续未完成的标题", "查看/修改已完成的标题"],
    horizontal=True
)

if "current_index" not in st.session_state:
    st.session_state.current_index = 0

if mode == "继续未完成的标题":
    remaining_df = df[~df["New ID"].astype(str).isin(answered_ids)].reset_index(drop=True)

    if len(remaining_df) == 0:
        st.success("这个 coder 已经完成所有标题。")
        st.stop()

    if st.session_state.current_index >= len(remaining_df):
        st.session_state.current_index = 0

    row = remaining_df.iloc[st.session_state.current_index]

else:
    if len(coder_answers) == 0:
        st.info("你还没有已完成的标题。")
        st.stop()

    selected_id = st.selectbox(
        "选择要查看/修改的 New ID:",
        coder_answers["New ID"].astype(str).tolist()
    )

    row = df[df["New ID"].astype(str) == str(selected_id)].iloc[0]

# =========================
# 显示题目
# =========================

new_id = row["New ID"]
title = row["Title"]

st.divider()
st.subheader(f"New ID: {new_id}")

st.markdown("### 这个标题属于下面哪个选项？")
st.markdown(f"> {title}")

previous_answer = None

if len(coder_answers) > 0:
    matched = coder_answers[coder_answers["New ID"].astype(str) == str(new_id)]
    if len(matched) > 0:
        previous_answer = matched.iloc[0]["answer_code"]

option_keys = list(OPTIONS.keys())

default_index = None
if previous_answer in option_keys:
    default_index = option_keys.index(previous_answer)

selected_code = st.radio(
    "请选择一个答案：",
    option_keys,
    format_func=lambda x: f"{x}. {OPTIONS[x]}",
    index=default_index if default_index is not None else 0
)

selected_label = OPTIONS[selected_code]

# =========================
# 保存
# =========================

col1, col2 = st.columns(2)

with col1:
    if st.button("保存答案", type="primary"):
        save_answer(
            worksheet=worksheet,
            coder=coder,
            new_id=new_id,
            title=title,
            answer_code=selected_code,
            answer_label=selected_label
        )
        st.success("已保存。")

        if mode == "继续未完成的标题":
            st.session_state.current_index += 1

        st.rerun()

with col2:
    if mode == "继续未完成的标题":
        if st.button("跳过这个标题"):
            st.session_state.current_index += 1
            st.rerun()

st.divider()

st.caption("A = Obesity-focused; B = Obesity-relevant; C = Health-focused; D = Weight-loss-focused; E = Diet-focused; F = Food-focused; G = About weight-loss medicine; H = About body image; I = About other disease.")
