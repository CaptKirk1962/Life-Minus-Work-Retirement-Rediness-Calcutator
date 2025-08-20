from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO

def generate_handbook(scores, archetype):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    def add_heading(text):
        story.append(Spacer(1, 12))
        story.append(Paragraph(f"<b>{text}</b>", styles["Heading2"]))
        story.append(Spacer(1, 6))

    def add_paragraph(text):
        story.append(Paragraph(text, styles["BodyText"]))
        story.append(Spacer(1, 12))

    story.append(Paragraph("Retirement Calculator Readiness Handbook", styles["Title"]))
    story.append(Paragraph("The Life Minus Work Roadmap", styles["Heading2"]))
    story.append(Paragraph("“Very Little Attention is Given to the Transition to Retirement”", styles["Italic"]))
    story.append(Spacer(1, 24))

    add_heading("Your Retirement Readiness Score")
    add_paragraph(f"Congratulations! Based on your responses, you are an: <b>{archetype}</b>")
    add_paragraph("You thrive on structure, vision, and impact. The shift from being “in control” to “in transition” can feel unsettling.")

    add_heading("Readiness Breakdown")
    for pillar, score in scores.items():
        if pillar != "Overall Score":
            add_paragraph(f"{pillar}: {score}/10")

    add_heading("Welcome to Life Minus Work")
    add_paragraph("The transition from work to life beyond career is a profound one—filled with new freedoms, and often, unexpected challenges. This roadmap is here to help you navigate this journey with clarity, courage, and a renewed sense of self.")

    doc.build(story)
    buffer.seek(0)
    return buffer