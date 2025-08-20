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

    # Cover
    story.append(Paragraph("Retirement Calculator Readiness Handbook", styles["Title"]))
    story.append(Paragraph("The Life Minus Work Roadmap", styles["Heading2"]))
    story.append(Paragraph("“Very Little Attention is Given to the Transition to Retirement”", styles["Italic"]))
    story.append(Spacer(1, 24))

    # Scores
    add_heading("Your Retirement Readiness Score")
    add_paragraph(f"Congratulations! Based on your responses, you are an: <b>{archetype}</b>")
    add_paragraph("You thrive on structure, vision, and impact. The shift from being “in control” to “in transition” can feel unsettling.")

    add_heading("Readiness Breakdown")
    for pillar, score in scores.items():
        if pillar != "Overall Score":
            add_paragraph(f"{pillar}: {score}/10")

    add_heading("Welcome to Life Minus Work")
    add_paragraph("The transition from work to life beyond career is a profound one—filled with new freedoms, and often, unexpected challenges. This roadmap is here to help you navigate this journey with clarity, courage, and a renewed sense of self.")

    steps = [
        {
            "title": "Step 1 – Reclaiming Your Time & Energy",
            "why": "You’ve earned the right to rest, reset, and redefine how you spend your time.",
            "example": "Angela, a former executive assistant, replaced her 8 a.m. team meetings with morning yoga and journaling.",
            "reflection": "Sketch your ideal day from morning to night. What do you need more of? What can you let go?",
            "action": "Block out 30 minutes each day this week just for you—no guilt, no tasks, no agenda."
        },
        {
            "title": "Step 2 – Rediscovering Identity",
            "why": "When your title fades, who are you really? Rediscovering your identity means reconnecting with the parts of you that existed before your job—and still do.",
            "example": "Mark, a retired airline captain, returned to painting after 35 years.",
            "reflection": "List 5 things you loved as a child. What’s one you’d love to revisit now?",
            "action": "Start one small creative or expressive project this week—just for yourself."
        },
        {
            "title": "Step 3 – Rebuilding Purpose",
            "why": "Purpose is what gets you up in the morning. After work, your purpose may shift—but it’s never gone.",
            "example": "Nina, a retired HR manager, began mentoring young women in her local business network.",
            "reflection": "What’s something you care deeply about? What change would you love to help bring about?",
            "action": "Explore one cause, group, or opportunity that aligns with your values."
        },
        {
            "title": "Step 4 – Strengthening Social Health",
            "why": "Loneliness can creep in during transitions. Intentional relationships keep us connected and vibrant.",
            "example": "Dave and two former colleagues created a monthly men’s circle—a casual dinner where they share, listen, and laugh.",
            "reflection": "Who are the top 3 people in your life right now? When’s the last time you really connected with them?",
            "action": "Send a message, schedule a coffee, or plan a walk this week."
        },
        {
            "title": "Step 5 – Reawakening Curiosity",
            "why": "Learning keeps your brain sharp and your spirit engaged. It reminds you that you’re still growing—at every age.",
            "example": "Sandra signed up for an online philosophy course.",
            "reflection": "What’s one thing you’ve always wanted to learn—just for the fun of it?",
            "action": "Search for a local or online class and enroll. Bonus: invite a friend to join you."
        },
        {
            "title": "Step 6 – Leaving a Legacy",
            "why": "Legacy isn’t just what you leave behind. It’s what you live now—how your presence shapes others’ lives.",
            "example": "George started recording video stories for his grandkids.",
            "reflection": "Write a letter to someone you’ve impacted. Reflect on what you want to be remembered for.",
            "action": "Start one act of legacy this week—mentor, volunteer, share your story, or document your journey."
        }
    ]

    for step in steps:
        add_heading(step["title"])
        add_paragraph(f"<b>Why It Matters:</b> {step['why']}")
        add_paragraph(f"<b>Real-Life Example:</b> {step['example']}")
        add_paragraph(f"<b>Reflection Exercise:</b> {step['reflection']}")
        add_paragraph(f"<b>Next Best Action:</b> {step['action']}")

    add_heading("About Life Minus Work")
    add_paragraph("Life Minus Work is more than a platform—it’s a movement to redefine what it means to thrive after your career.")
    add_paragraph("Whether you're stepping away from a long career or simply exploring what's next, we're here to help you:")
    add_paragraph("- Find purpose beyond a job title")
    add_paragraph("- Build meaningful connections")
    add_paragraph("- Reignite curiosity and creativity")
    add_paragraph("- Stay healthy and inspired")
    add_paragraph("Join our growing community of thoughtful explorers designing their next chapter—together.")
    add_paragraph("👉 Download the full book: lifeminuswork.com/join")

    doc.build(story)
    buffer.seek(0)
    return buffer