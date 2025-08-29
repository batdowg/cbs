BADGE_CHOICES = [
    ("", "None"),
    ("Foundations", "Foundations"),
    ("Practitioner", "Practitioner"),
    ("Advanced", "Advanced"),
    ("Expert", "Expert"),
    ("Coach", "Coach"),
    ("Facilitator", "Facilitator"),
    ("Program Leader", "Program Leader"),
]

LANGUAGE_NAMES = [
    "Chinese",
    "Dutch",
    "English",
    "French",
    "German",
    "Japanese",
    "Spanish",
]

MAGIC_LINK_TTL_DAYS = 30

# Default password for newly created Client Session Administrator accounts
DEFAULT_CSA_PASSWORD = "KTRocks!CSA"

PERMISSIONS_MATRIX = {
    "columns": [
        "App_Admin",
        "is_kt_admin",
        "is_kcrm",
        "is_kt_delivery",
        "is_kt_contractor",
        "is_kt_staff",
    ],
    "rows": {
        "Resources (Settings)": {
            "App_Admin": "V/E/D",
            "is_kt_admin": "V/E/D",
            "is_kcrm": "—",
            "is_kt_delivery": "V/E",
            "is_kt_contractor": "V",
            "is_kt_staff": "—",
        },
        "Workshop Types (Edit, Prework)": {
            "App_Admin": "V/E",
            "is_kt_admin": "V/E",
            "is_kcrm": "—",
            "is_kt_delivery": "—",
            "is_kt_contractor": "—",
            "is_kt_staff": "—",
        },
        "Sessions (View, Edit, Prework Send)": {
            "App_Admin": "V/E/Send",
            "is_kt_admin": "V/E/Send",
            "is_kcrm": "V",
            "is_kt_delivery": "V",
            "is_kt_contractor": "V",
            "is_kt_staff": "V",
        },
        "Materials": {
            "App_Admin": "V/E",
            "is_kt_admin": "V/E",
            "is_kcrm": "V/E",
            "is_kt_delivery": "V",
            "is_kt_contractor": "V",
            "is_kt_staff": "V",
        },
        "Surveys": {
            "App_Admin": "V/E",
            "is_kt_admin": "V/E",
            "is_kcrm": "V",
            "is_kt_delivery": "V",
            "is_kt_contractor": "V",
            "is_kt_staff": "V",
        },
        "Users": {
            "App_Admin": "V/E/D",
            "is_kt_admin": "V/E",
            "is_kcrm": "—",
            "is_kt_delivery": "—",
            "is_kt_contractor": "—",
            "is_kt_staff": "—",
        },
        "Importer": {
            "App_Admin": "V",
            "is_kt_admin": "V",
            "is_kcrm": "—",
            "is_kt_delivery": "—",
            "is_kt_contractor": "—",
            "is_kt_staff": "—",
        },
        "Certificates (Issue, View)": {
            "App_Admin": "Issue/V",
            "is_kt_admin": "Issue/V",
            "is_kcrm": "V",
            "is_kt_delivery": "V",
            "is_kt_contractor": "V",
            "is_kt_staff": "V",
        },
        "Verify Certificates": {
            "App_Admin": "V",
            "is_kt_admin": "V",
            "is_kcrm": "V",
            "is_kt_delivery": "V",
            "is_kt_contractor": "V",
            "is_kt_staff": "V",
        },
        "Settings (App Admin)": {
            "App_Admin": "V/E",
            "is_kt_admin": "—",
            "is_kcrm": "—",
            "is_kt_delivery": "—",
            "is_kt_contractor": "—",
            "is_kt_staff": "—",
        },
        "My Resources": {
            "App_Admin": "V",
            "is_kt_admin": "V",
            "is_kcrm": "V",
            "is_kt_delivery": "V",
            "is_kt_contractor": "V",
            "is_kt_staff": "V",
        },
        "My Workshops": {
            "App_Admin": "V",
            "is_kt_admin": "V",
            "is_kcrm": "V",
            "is_kt_delivery": "V",
            "is_kt_contractor": "V",
            "is_kt_staff": "V",
        },
        "My Profile": {
            "App_Admin": "V/E",
            "is_kt_admin": "V/E",
            "is_kcrm": "V/E",
            "is_kt_delivery": "V/E",
            "is_kt_contractor": "V/E",
            "is_kt_staff": "V/E",
        },
    },
}
