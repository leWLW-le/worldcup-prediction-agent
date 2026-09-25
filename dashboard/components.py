import pandas as pd
import streamlit as st


def show_result(result):
    st.caption(
        f"数据截止 {result['as_of']} · 状态 {result['status']} · 模型 {result['model_version']}"
    )
    for warning in result.get("warnings", []):
        st.warning(warning)
    st.metric("最高夺冠概率球队", result["champion"], f"{result['champion_probability']:.1%}")
    probabilities = pd.DataFrame(
        [{"球队": t, "夺冠概率": p} for t, p in result["champion_distribution"].items()]
    )
    st.bar_chart(probabilities.set_index("球队"))
    st.write("代表路径冠军", result["representative_path_champion"])
    st.caption("代表路径与最高概率球队可以不同；模拟采样误差不包含模型误差。")
    st.dataframe(result["representative_path"], use_container_width=True)
    if "probability_change" in result:
        st.dataframe([{"球队": t, "概率变化": p} for t, p in result["probability_change"].items()])
    with st.expander("运行记录与完整结果"):
        st.json(result)
