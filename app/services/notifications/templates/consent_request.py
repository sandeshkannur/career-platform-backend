# app/services/notifications/templates/consent_request.py
#
# Guardian consent request email. Text below is the reviewed copy — verbatim,
# character for character, as supplied. Do not rewrite, "improve", or
# retranslate it. Placeholders are filled via str.format(): student_name,
# otp, verification_url.
#
# NOTE: the Privacy Policy URL referenced below (https://mapyourcareer.in/privacy)
# does not exist yet — it currently 200s but serves only the SPA shell with no
# privacy content. DPDP requires the consent notice to state how consent can
# be withdrawn, so the line stays in the template regardless. This page must
# be built before any real guardian is emailed.

CONSENT_REQUEST_TEMPLATES = {
    "en": {
        "subject": "Your consent is needed for your child's account — MapYourCareer",
        "text": """Hello,

{student_name} has created an account on MapYourCareer. Since they are under 18, we require your consent to collect and use their personal information (such as name, age, and career interests) in order to provide career guidance services.

If you are their parent or guardian, please open the link below and enter this code:

Code: {otp}

{verification_url}

This code expires in 30 minutes.

If you do not wish to give consent, please ignore this email. No action will be taken.

You may withdraw your consent at any time. For more information, please read our Privacy Policy: https://mapyourcareer.in/privacy

If you have questions, write to support@mapyourcareer.in

Thank you,
MYC Edtech LLP""",
    },
    "kn": {
        "subject": "ನಿಮ್ಮ ಮಗುವಿನ ಖಾತೆಗೆ ನಿಮ್ಮ ಒಪ್ಪಿಗೆ ಅಗತ್ಯವಿದೆ — MapYourCareer",
        "text": """ನಮಸ್ಕಾರ,

{student_name} ಎಂಬವರು MapYourCareer ವೇದಿಕೆಯಲ್ಲಿ ಖಾತೆಯನ್ನು ತೆರೆದಿದ್ದಾರೆ. ಅವರು 18 ವರ್ಷಕ್ಕಿಂತ ಕಡಿಮೆ ವಯಸ್ಸಿನವರಾಗಿರುವುದರಿಂದ, ಅವರ ವೈಯಕ್ತಿಕ ಮಾಹಿತಿಯನ್ನು (ಹೆಸರು, ವಯಸ್ಸು, ಮತ್ತು ವೃತ್ತಿ ಆಸಕ್ತಿಗಳು) ವೃತ್ತಿ ಮಾರ್ಗದರ್ಶನ ಸೇವೆ ಒದಗಿಸಲು ಬಳಸಲು ನಿಮ್ಮ ಒಪ್ಪಿಗೆ ಅಗತ್ಯವಿದೆ.

ನೀವು ಅವರ ಪೋಷಕರು ಅಥವಾ ಪಾಲಕರಾಗಿದ್ದರೆ, ದಯವಿಟ್ಟು ಕೆಳಗಿನ ಲಿಂಕ್ ತೆರೆದು ಈ ಕೋಡ್ ಅನ್ನು ನಮೂದಿಸಿ:

ಕೋಡ್: {otp}

{verification_url}

ಈ ಕೋಡ್ 30 ನಿಮಿಷಗಳಲ್ಲಿ ಅವಧಿ ಮುಗಿಯುತ್ತದೆ.

ನೀವು ಒಪ್ಪಿಗೆ ನೀಡಲು ಇಚ್ಛಿಸದಿದ್ದರೆ, ಈ ಇಮೇಲ್ ಅನ್ನು ನಿರ್ಲಕ್ಷಿಸಿ. ಯಾವುದೇ ಕ್ರಮ ತೆಗೆದುಕೊಳ್ಳಲಾಗುವುದಿಲ್ಲ.

ನೀವು ಯಾವುದೇ ಸಮಯದಲ್ಲಿ ನಿಮ್ಮ ಒಪ್ಪಿಗೆಯನ್ನು ಹಿಂತೆಗೆದುಕೊಳ್ಳಬಹುದು. ಹೆಚ್ಚಿನ ಮಾಹಿತಿಗಾಗಿ, ನಮ್ಮ ಗೌಪ್ಯತಾ ನೀತಿಯನ್ನು ಓದಿ: https://mapyourcareer.in/privacy

ಪ್ರಶ್ನೆಗಳಿದ್ದರೆ support@mapyourcareer.in ಗೆ ಬರೆಯಿರಿ.

ಧನ್ಯವಾದಗಳು,
MYC Edtech LLP""",
    },
}
