"""GUI Pages Package"""

from .dashboard_page import DashboardPage
from .enrollment_page import MultiPhotoEnrollmentPage
from .photo_import_page import PhotoImportPage
from .review_page import ReviewPage
from .share_page import SharePage
from .license_page import LicensePage

__all__ = [
    'DashboardPage',
    'EnrollmentPage',
    'PhotoImportPage',
    'ReviewPage',
    'SharePage',
    'LicensePage'
]