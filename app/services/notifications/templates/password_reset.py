# app/services/notifications/templates/password_reset.py
#
# Password reset email. UNUSED this branch — no route calls this template
# yet. Written now so the reset feature has rails to land on.
#
# Placeholders (str.format()): user_name, reset_url.
#
# CONFIDENCE NOTE: English copy is original, written for this task, unreviewed.
# Kannada copy is machine-assisted (my own translation), NOT reviewed by a
# native speaker. Confidence is medium for the straightforward operational
# sentences (reset link, expiry, ignore-if-not-you) and lower for phrasing
# choices like "ಮರುಹೊಂದಿಸಲು ವಿನಂತಿ ಬಂದಿದೆ" (request has arrived to reset) —
# a native speaker should sanity-check tone/formality before this ships.

PASSWORD_RESET_TEMPLATES = {
    "en": {
        "subject": "Reset your MapYourCareer password",
        "text": """Hello {user_name},

We received a request to reset your MapYourCareer password.

If this was you, open the link below to choose a new password:

{reset_url}

This link expires in 30 minutes.

If you did not request this, you can safely ignore this email — your password will not be changed.

If you have questions, write to support@mapyourcareer.in

Thank you,
MYC Edtech LLP""",
    },
    "kn": {
        "subject": "ನಿಮ್ಮ MapYourCareer ಪಾಸ್‌ವರ್ಡ್ ಮರುಹೊಂದಿಸಿ",
        "text": """ನಮಸ್ಕಾರ {user_name},

ನಿಮ್ಮ MapYourCareer ಪಾಸ್‌ವರ್ಡ್ ಅನ್ನು ಮರುಹೊಂದಿಸಲು ವಿನಂತಿ ಬಂದಿದೆ.

ಇದು ನೀವೇ ಆಗಿದ್ದರೆ, ಹೊಸ ಪಾಸ್‌ವರ್ಡ್ ಆಯ್ಕೆ ಮಾಡಲು ಕೆಳಗಿನ ಲಿಂಕ್ ತೆರೆಯಿರಿ:

{reset_url}

ಈ ಲಿಂಕ್ 30 ನಿಮಿಷಗಳಲ್ಲಿ ಅವಧಿ ಮುಗಿಯುತ್ತದೆ.

ನೀವು ಇದನ್ನು ವಿನಂತಿಸದಿದ್ದರೆ, ಈ ಇಮೇಲ್ ಅನ್ನು ನಿರ್ಲಕ್ಷಿಸಬಹುದು — ನಿಮ್ಮ ಪಾಸ್‌ವರ್ಡ್ ಬದಲಾಗುವುದಿಲ್ಲ.

ಪ್ರಶ್ನೆಗಳಿದ್ದರೆ support@mapyourcareer.in ಗೆ ಬರೆಯಿರಿ.

ಧನ್ಯವಾದಗಳು,
MYC Edtech LLP""",
    },
}
