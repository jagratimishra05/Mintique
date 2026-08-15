from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from nftapp.models import NFT, Category
from walletapp.models import Wallet

import io
from PIL import Image

User = get_user_model()

DEMO_NFTS = [
    ("Cosmic Drift #047", "AstralArtist", Category.ART, "2.4", (124, 92, 252)),
    ("Quantum Void #001", "NeuralBrush", Category.ART, "6.9", (30, 30, 60)),
    ("Digital Soul #091", "CryptoVision", Category.PHOTOGRAPHY, "4.2", (79, 195, 247)),
    ("Neon Horizon #012", "PixelForge", Category.ART, "1.1", (255, 182, 72)),
    ("Silent Echo #003", "SoundWave", Category.MUSIC, "0.8", (74, 222, 128)),
    ("Chrono Fragment #077", "TimeKeeper", Category.COLLECTIBLE, "3.3", (255, 107, 107)),
]


class Command(BaseCommand):
    help = "Seed the database with a demo creator account and sample NFTs."

    def handle(self, *args, **options):
        demo_user, created = User.objects.get_or_create(
            email="demo@mintique.io",
            defaults={"username": "demo_creator", "first_name": "Demo", "last_name": "Creator"},
        )
        if created:
            demo_user.set_password("DemoPass123!")
            demo_user.wallet_address = "0xDEMO00000000000000000000000000000DEMO0"
            demo_user.save()
            self.stdout.write(self.style.SUCCESS("Created demo@mintique.io / DemoPass123!"))

        Wallet.objects.get_or_create(user=demo_user, defaults={"eth_balance": 50, "mnq_balance": 5000})

        for name, creator, category, price, color in DEMO_NFTS:
            if NFT.objects.filter(name=name).exists():
                continue
            buf = io.BytesIO()
            Image.new("RGB", (500, 500), color).save(buf, format="PNG")
            nft = NFT(
                owner=demo_user, creator_name=creator, name=name,
                description=f"A striking piece from the {creator} series, minted on Mintique.",
                category=category, price=Decimal(price), is_listed=True,
            )
            nft.image.save(f"{name.replace(' ', '_').replace('#','')}.png", ContentFile(buf.getvalue()), save=False)
            nft.save()
            self.stdout.write(self.style.SUCCESS(f"Seeded {name}"))

        self.stdout.write(self.style.SUCCESS("Done."))
