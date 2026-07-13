# app/services/notifications/templates/password_reset.py
#
# Password reset email, sent by POST /v1/auth/forgot-password/request
# (channel="email"). Follows the same JWT+OTP-hash pattern as guardian
# consent (app/utils/consent_request.py): the link alone is not enough to
# reset the password — the recipient must also enter the OTP code shown
# below, which only reaches them via this fixed destination.
#
# Placeholders (str.format()): user_name, otp, reset_url.
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

If this was you, open the link below and enter this code to choose a new password:

Code: {otp}

{reset_url}

This code and link expire in 30 minutes.

If you did not request this, you can safely ignore this email — your password will not be changed.

If you have questions, write to support@mapyourcareer.in

Thank you,
MYC Edtech LLP""",
    },
    "kn": {
        "subject": "ನಿಮ್ಮ MapYourCareer ಪಾಸ್‌ವರ್ಡ್ ಮರುಹೊಂದಿಸಿ",
        "text": """ನಮಸ್ಕಾರ {user_name},

ನಿಮ್ಮ MapYourCareer ಪಾಸ್‌ವರ್ಡ್ ಅನ್ನು ಮರುಹೊಂದಿಸಲು ವಿನಂತಿ ಬಂದಿದೆ.

ಇದು ನೀವೇ ಆಗಿದ್ದರೆ, ಹೊಸ ಪಾಸ್‌ವರ್ಡ್ ಆಯ್ಕೆ ಮಾಡಲು ಕೆಳಗಿನ ಲಿಂಕ್ ತೆರೆದು ಈ ಕೋಡ್ ಅನ್ನು ನಮೂದಿಸಿ:

ಕೋಡ್: {otp}

{reset_url}

ಈ ಕೋಡ್ ಮತ್ತು ಲಿಂಕ್ 30 ನಿಮಿಷಗಳಲ್ಲಿ ಅವಧಿ ಮುಗಿಯುತ್ತದೆ.

ನೀವು ಇದನ್ನು ವಿನಂತಿಸದಿದ್ದರೆ, ಈ ಇಮೇಲ್ ಅನ್ನು ನಿರ್ಲಕ್ಷಿಸಬಹುದು — ನಿಮ್ಮ ಪಾಸ್‌ವರ್ಡ್ ಬದಲಾಗುವುದಿಲ್ಲ.

ಪ್ರಶ್ನೆಗಳಿದ್ದರೆ support@mapyourcareer.in ಗೆ ಬರೆಯಿರಿ.

ಧನ್ಯವಾದಗಳು,
MYC Edtech LLP""",
    },
}
