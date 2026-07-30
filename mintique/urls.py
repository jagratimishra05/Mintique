from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from nftapp.views import about_view, contact_view, home_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", home_view, name="home"),
    path("about/", about_view, name="about"),
    path("contact/", contact_view, name="contact"),
    path("accounts/", include("accounts.urls")),
    path("nft/", include("nftapp.urls")),
    path("wallet/", include("walletapp.urls")),
]

if settings.DEBUG:
    # Only MEDIA needs manual wiring in dev (user-uploaded NFT images etc).
    # STATIC files (CSS/JS) are now handled by WhiteNoise middleware in all
    # environments — the old `static(settings.STATIC_URL, ...)` line here
    # pointed at STATIC_ROOT, which is empty until `collectstatic` is run,
    # so it silently 404'd whenever DEBUG was False and nothing else was
    # serving static files. That's the root cause of the "still white"
    # background no matter what was changed in style.css.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
