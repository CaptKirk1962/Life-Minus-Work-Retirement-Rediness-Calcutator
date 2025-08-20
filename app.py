import streamlit as st
from handbook_generator import generate_handbook
import pandas as pd

st.set_page_config(page_title="Life Minus Work Readiness Quiz")
st.title("🌟 Life Minus Work Readiness Quiz")

# Ask for user's name
user_name = st.text_input("👋 What's your first name?", max_chars=30)

if user_name:
    st.markdown("Rate each statement from **1 (Strongly Disagree)** to **5 (Strongly Agree)**")
    pillar_questions = {
        "Purpose & Identity": [
            "I feel confident about who I am beyond my work role.",
            "I have a clear sense of purpose for my post-work life.",
            "I rarely feel anxious or lost without my daily work routine.",
            "I can easily reflect on my career achievements without regret."
        ],
        "Social Health & Community Connection": [
            "I have strong relationships outside of work.",
            "I actively nurture friendships and community connections.",
            "I feel comfortable reaching out to new people.",
            "Loneliness is not a concern for me right now."
        ],
        "Health & Vitality": [
            "I maintain regular physical activity.",
            "My mental and emotional wellbeing feels stable.",
            "I prioritize sleep, nutrition, and stress management.",
            "I have no major health barriers to exploring new activities."
        ],
        "Learning & Growth": [
            "I actively pursue new knowledge or skills.",
            "I have a growth mindset and enjoy learning challenges.",
            "I make time for reading, courses, or hobbies that expand my mind.",
            "Cognitive sharpness is a priority in my daily life."
        ],
        "Adventure & Exploration": [
            "I seek out new experiences and adventures regularly.",
            "I feel excited about exploring unfamiliar places or activities.",
            "Novelty and discovery bring joy to my routine.",
            "I step outside my comfort zone without much hesitation."
        ],
        "Giving Back": [
            "I find ways to contribute to others or my community.",
            "Mentoring or volunteering feels fulfilling to me.",
            "I have opportunities to share my wisdom and experience.",
            "Giving back is an important part of my identity."
        ]
    }

    ratings = {}
    for pillar, questions in pillar_questions.items():
        st.subheader(pillar)
        ratings[pillar] = [st.slider(q, 1, 5, 3, key=f"{pillar}-{i}") for i, q in enumerate(questions)]

    if st.button("🔍 Calculate My Readiness"):
        def get_score(ratings):
            return round(sum(ratings) / len(ratings) * 2, 1)

        scores = {pillar: get_score(vals) for pillar, vals in ratings.items()}
        scores["Overall Score"] = round(sum(scores.values()) / 6, 1)

        archetype = "Executive Type" if scores["Purpose & Identity"] >= 6 else "Explorer Type"

        st.markdown("### 📊 Readiness Scores")
        df = pd.DataFrame.from_dict(scores, orient="index", columns=["Score"])
        st.table(df)

        st.markdown(f"### 🧭 You are an: **{archetype}**")

        # Generate PDF with name
        pdf = generate_handbook(scores, archetype, user_name)
        st.download_button("📄 Download My Personalized Handbook (PDF)", data=pdf, file_name="life_minus_work_handbook.pdf", mime="application/pdf")
else:
    st.info("Please enter your first name to begin.")