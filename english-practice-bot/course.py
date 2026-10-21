"""Pre-Intermediate Level Speaking Topics — 100-set video course.

Sets are (number, english_title). Media file_ids live in
course_file_ids.json ({"video": {n: file_id}, "pdf": {n: file_id}}),
seeded by upload_course_media.py. Videos and worksheets are always
sent with protect_content so students cannot save or forward them.
"""
import json
import os

COURSE_NAME = "Pre-Intermediate Level Speaking Topics"
PAGE_SIZE = 10

SETS = [
    (1, "Greetings & introductions"),
    (2, "Everyday phrases"),
    (3, "Numbers & counting"),
    (4, "Restaurant"),
    (5, "Beginner practice (mixed)"),
    (6, "Shopping"),
    (7, "Directions"),
    (8, "Hotel"),
    (9, "Food & tastes"),
    (10, "Health & doctor"),
    (11, "Small talk"),
    (12, "Time & schedules"),
    (13, "Weather"),
    (14, "Daily routines"),
    (15, "Emergencies"),
    (16, "Work & jobs"),
    (17, "Family"),
    (18, "Travel"),
    (19, "Money & payments"),
    (20, "Phone calls"),
    (21, "Feelings & emotions"),
    (22, "Hobbies"),
    (23, "Describing people"),
    (24, "Colors"),
    (25, "Animals"),
    (26, "Ordering food & drink"),
    (27, "Clothes & appearance"),
    (28, "Problems & broken things"),
    (29, "Making appointments"),
    (30, "Bank"),
    (31, "Renting a house"),
    (32, "Market"),
    (33, "Taxi"),
    (34, "Airport"),
    (35, "Pharmacy"),
    (36, "Clothes & shoes"),
    (37, "Barber & hair salon"),
    (38, "Phone, SIM & internet"),
    (39, "Post office"),
    (40, "Temple & religion"),
    (41, "School & education"),
    (42, "Job interview"),
    (43, "Visa & immigration"),
    (44, "Driving"),
    (45, "Gas station"),
    (46, "Repair shop"),
    (47, "House chores"),
    (48, "Cooking"),
    (49, "Fruits"),
    (50, "Vegetables"),
    (51, "Drinks & desserts"),
    (52, "Festivals"),
    (53, "Sports"),
    (54, "Gym & exercise"),
    (55, "Social media"),
    (56, "Computer problems"),
    (57, "Nature & environment"),
    (58, "Body parts"),
    (59, "Dentist"),
    (60, "Visiting a patient"),
    (61, "Children & parenting"),
    (62, "Wedding"),
    (63, "Making friends"),
    (64, "Dating"),
    (65, "Compliments"),
    (66, "Apologizing"),
    (67, "Complaints"),
    (68, "Bargaining"),
    (69, "Dates & calendar"),
    (70, "Sizes & measurements"),
    (71, "Public transport"),
    (72, "Booking tickets"),
    (73, "Places in town"),
    (74, "Library"),
    (75, "Camping & nature"),
    (76, "Music"),
    (77, "Art"),
    (78, "Laundry"),
    (79, "Utility bills"),
    (80, "Neighbors"),
    (81, "Borrowing & lending"),
    (82, "Invitations"),
    (83, "Parties"),
    (84, "Wishes & congratulations"),
    (85, "Future plans"),
    (86, "Childhood memories"),
    (87, "Opinions"),
    (88, "Giving advice"),
    (89, "Comparing things"),
    (90, "Superlatives"),
    (91, "Asking permission"),
    (92, "Offering help"),
    (93, "News & media"),
    (94, "Sick leave"),
    (95, "Money problems"),
    (96, "Lost & found"),
    (97, "Exams & tests"),
    (98, "Grand review 1"),
    (99, "Grand review 2"),
    (100, "Grand review 3"),
]

_FILE_IDS = None


def file_ids():
    """Load {video: {n: file_id}, pdf: {n: file_id}} (cached)."""
    global _FILE_IDS
    if _FILE_IDS is None:
        try:
            with open(os.path.join(os.path.dirname(__file__),
                         "course_file_ids.json"), encoding="utf-8") as f:
                _FILE_IDS = json.load(f)
        except (OSError, ValueError):
            _FILE_IDS = {"video": {}, "pdf": {}}
    return _FILE_IDS


def media_for(n):
    """(video_file_id, pdf_file_id) for set n; None when not seeded yet."""
    ids = file_ids()
    v = (ids.get("video") or {}).get(str(n))
    p = (ids.get("pdf") or {}).get(str(n))
    return v, p


def num_pages():
    return (len(SETS) + PAGE_SIZE - 1) // PAGE_SIZE


def course_keyboard(page=0):
    """Inline keyboard: 10 sets per page, starting from Set 1 at the top."""
    page = max(0, min(page, num_pages() - 1))
    start = page * PAGE_SIZE
    buttons = []
    for n, title in SETS[start:start + PAGE_SIZE]:
        buttons.append([{"text": f"{n}. {title}",
                            "callback_data": f"course:s:{n}"}])
    nav = []
    if page > 0:
        nav.append({"text": "⬅️ Prev", "callback_data": f"course:p:{page - 1}"})
    if page < num_pages() - 1:
        nav.append({"text": "Next ➡️", "callback_data": f"course:p:{page + 1}"})
    if nav:
        buttons.append(nav)
    return {"inline_keyboard": buttons}


def course_intro():
    return (f"📚 {COURSE_NAME}\n\n"
            "100 video lessons — pick a set to start. "
            "Each set has a speaking video + worksheet. 👇")

