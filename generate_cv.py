import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

# Output PDF path (project root)
output_path = os.path.abspath('misbah_cv.pdf')

# --- Sample CV Data (replace with real details) ---
name = "Misbah Ullah"
contact = "Phone: +92-300-1234567 | Email: misbah@example.com | Location: Pakistan"
summary = "AI & Machine Learning Engineer with 3+ years of experience building computer vision and deep learning solutions. Passionate about creating impactful AI products."
skills = ["Python", "TensorFlow", "PyTorch", "OpenCV", "Computer Vision", "Deep Learning", "Flask", "SQL"]
experience = [
    {"role": "AI Engineer", "company": "Tech Solutions", "period": "Jan 2022 – Present", "details": "Developed end‑to‑end computer vision pipelines, optimized models for inference, and integrated AI services into web applications."},
    {"role": "Machine Learning Intern", "company": "Innovate Labs", "period": "Jun 2021 – Dec 2021", "details": "Implemented image classification models, performed data augmentation, and contributed to research publications."}
]
education = [
    {"degree": "BSc Computer Science", "institution": "University of Punjab", "year": "2018 – 2022", "details": "CGPA: 3.8/4.0"}
]
projects = [
    {"title": "Real‑time Object Detection", "description": "Built a YOLO‑v5 based detection system for traffic monitoring, achieving 92% mAP."},
    {"title": "Face Mask Detector", "description": "Implemented a lightweight CNN for detecting face masks in live video streams."}
]

# Create PDF document
doc = SimpleDocTemplate(output_path, pagesize=A4,
                        rightMargin=40, leftMargin=40,
                        topMargin=60, bottomMargin=40)
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='Header', fontSize=20, leading=24, spaceAfter=12, alignment=1, textColor=colors.HexColor('#5fbcb8')))
styles.add(ParagraphStyle(name='SubHeader', fontSize=14, leading=18, spaceAfter=6, textColor=colors.HexColor('#5fbcb8')))
styles.add(ParagraphStyle(name='NormalBold', parent=styles['Normal'], fontName='Helvetica-Bold'))

story = []
# Name & Contact
story.append(Paragraph(name, styles['Header']))
story.append(Paragraph(contact, styles['Normal']))
story.append(Spacer(1, 12))
# Summary
story.append(Paragraph('Summary', styles['SubHeader']))
story.append(Paragraph(summary, styles['Normal']))
story.append(Spacer(1, 12))
# Skills
story.append(Paragraph('Skills', styles['SubHeader']))
skill_table = Table([ [', '.join(skills)] ], colWidths=[450])
skill_table.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,-1), colors.whitesmoke),
    ('BOX', (0,0), (-1,-1), 0.5, colors.gray)
]))
story.append(skill_table)
story.append(Spacer(1, 12))
# Experience
story.append(Paragraph('Experience', styles['SubHeader']))
for exp in experience:
    story.append(Paragraph(f"<b>{exp['role']}</b> – {exp['company']} ({exp['period']})", styles['NormalBold']))
    story.append(Paragraph(exp['details'], styles['Normal']))
    story.append(Spacer(1, 6))
story.append(Spacer(1, 12))
# Education
story.append(Paragraph('Education', styles['SubHeader']))
for edu in education:
    story.append(Paragraph(f"<b>{edu['degree']}</b>, {edu['institution']} ({edu['year']})", styles['NormalBold']))
    story.append(Paragraph(edu['details'], styles['Normal']))
    story.append(Spacer(1, 6))
story.append(Spacer(1, 12))
# Projects
story.append(Paragraph('Projects', styles['SubHeader']))
for proj in projects:
    story.append(Paragraph(f"<b>{proj['title']}</b>", styles['NormalBold']))
    story.append(Paragraph(proj['description'], styles['Normal']))
    story.append(Spacer(1, 6))

# Build the PDF
doc.build(story)
print('PDF generated at', output_path)
