import time
import json
import requests
from collections import defaultdict
from time import sleep as wait
import os
# --- CONFIG ---
SERVER_URL = "http://localhost:51483"
WAIT_TIME = 2  # seconds between actions

resultData = defaultdict(list)
skippedProducts = defaultdict(list)

LWA_CLIENT_ID = "amzn1.application-oa2-client.5b8b71c8ff56492cbfe3e76508df84b9"
LWA_CLIENT_SECRET = (
    "amzn1.oa2-cs.v1.125f7e93012c23220035b57432b735034172c90f8adfa7e8d02c97404102dec6"
)

LWA_REFRESH_TOKEN = "Atzr|IwEBIIoBKW7BXRrH_RjDUHWYBtJKOwtqYxX9q5nmnuMa1xmvhkamOJGkVoDNrDoWVuHQ6ZFPGPeTJTCVigrQXOcoKniwmrkZyiFrg1chn0O0rfoi7_Rycfu6RwjgT73m-Tnf4lq60O8_gIhMrDjX-aCsKe7vI8MKMTyypijJTP6m19P5n0nzCP03RgTaRa-i_zztsWxy3cPPMLnbv0KiagmsuiXhvTv6Idp7OWkdMK6inBqTm3c6xdhRH5Qz6NvDcbiHPOJl68bvDdtDleZO9Xe_Ijw1Z29oOfRWyOqSEtNRc0nhmCXCDhwAy11gM067l_Wtfz2JwjxgthxW1oRgP29IvHig"

class AmazonProductChecker:
    def __init__(self, client_id, client_secret, refresh_token, server_url, wait_time):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.server_url = server_url
        self.wait_time = wait_time
        self.access_token = self.get_access_token()
        self.result_data = defaultdict(list)
        self.skipped_products = defaultdict(list)

    def get_access_token(self):
        url = "https://api.amazon.com/auth/o2/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        response = requests.post(url, data=data)
        print("Access token response:", response.text)
        response.raise_for_status()
        return response.json()["access_token"]

    def refresh_access_token(self):
        self.access_token = self.get_access_token()
        print("Access token refreshed.")

    def title_to_asin(self, title, marketplace_id="ATVPDKIKX0DER"):
        url = (
            f"https://sellingpartnerapi-na.amazon.com/catalog/2022-04-01/items"
            f"?keywords={requests.utils.quote(title)}&marketplaceIds={marketplace_id}"
        )
        headers = {"accept": "application/json", "x-amz-access-token": self.access_token}

        try:
            response = requests.get(url, headers=headers)
            data = response.json()

            if "items" in data and len(data["items"]) > 0:
                asin = data["items"][0].get("asin")
                return asin
            else:
                print(f"No ASIN found for title: {title}")
                return None
        except Exception as e:
            print(f"Error searching title '{title}': {e}")
            return None

    def check_restrictions(self, asin):
        url = f"https://sellingpartnerapi-na.amazon.com/listings/2021-08-01/restrictions?asin={asin}&conditionType=new_new&sellerId=A2TR1ONI5QOLW4&marketplaceIds=ATVPDKIKX0DER&reasonLocale=en_US"

        headers = {
            "accept": "application/json",
            "x-amz-access-token": self.access_token,
        }

        try:
            response = requests.get(url, headers=headers)
            data = response.json()
            print(f"Response for ASIN {asin}: {data}")
            if "errors" in data and data["errors"][0].get("code") == "Unauthorized":
                print("Access token expired, refreshing...")
                self.refresh_access_token()
                # Retry once
                response = requests.get(url, headers=headers)
                data = response.json()
            return data
        except Exception as e:
            print(f"Unexpected error checking ASIN {asin}: {e}")
            return {"errors": [{"message": str(e)}]}

    def fetch_search_keys_from_server(self):
        try:
            resp = requests.get(f"{self.server_url}/search-key")
            data = resp.json()
            print(data)
            if isinstance(data.get("data"), list):
                return [str(s).strip() for s in data["data"] if str(s).strip()]
            return []
        except Exception as e:
            print(f"Failed to fetch search key from server: {e}")
            return []

    def send_checked_data_to_server(self, results, skipped):
        with open("resultData.json", "r") as f:
            existing_data = json.load(f)
            payload = {"results": existing_data, "skipped": []}

        try:
            resp = requests.post(
                f"{self.server_url}/checkeddata",
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
            )
            if resp.status_code == 200:
                print("✅ Checked data sent to server.")
            else:
                print(f"⚠️ Server responded with status {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"❌ Failed to send checked data to server: {e}")

    def process_titles(self, titles):
        counter = 0
        for title in titles:
            counter += 1
            if counter % 100 == 0:
                print("Refreshing access token...")
                self.refresh_access_token()
            asin = self.title_to_asin(title)
            if not asin:
                print(f"No ASIN found for title: {title}, skipping...")
                self.skipped_products["skippid"].append({"productUPC": title})
                continue
            wait(self.wait_time + 1)
            print(f"Checking: {title} - ASIN: {asin}")
            data = self.check_restrictions(asin)

            # Ensure asinsdata.json exists
            if not os.path.exists("asinsdata.json"):
                with open("asinsdata.json", "w") as f:
                    json.dump({}, f)

            # Load old data
            try:
                with open("asinsdata.json", "r") as f:
                    old_data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                old_data = {}

            # Merge
            old_data[title] = data
            with open("asinsdata.json", "w") as f:
                json.dump(old_data, f, indent=4)

            if "errors" in data:
                self.skipped_products["skippid"].append({"productUPC": title})
            elif not data.get("restrictions"):
                self.result_data[title].append(
                    {
                        "productASIN": asin,
                        "status": "✅ You can sell this item!",
                    }
                )
            else:
                reason_info = data["restrictions"][0].get("reasons", [])[0]
                reason_code = reason_info.get("reasonCode", "")
                message = reason_info.get("message", "")

                if reason_code == "NOT_ELIGIBLE":
                    self.result_data[title].append(
                        {
                            "productASIN": asin,
                            "status": f"❌ {message} You are not eligible to sell this product.",
                        }
                    )
                elif reason_code == "APPROVAL_REQUIRED":
                    self.result_data[title].append(
                        {
                            "productASIN": asin,
                            "status": f"⚠️ Apply to sell. Approval is required. {message}",
                        }
                    )
                else:
                    self.result_data[title].append(
                        {
                            "productASIN": asin,
                            "status": f"ℹ️ Status unknown. Reason: {message}",
                        }
                    )

        # Save resultData.json
        with open("resultData.json", "w") as f:
            json.dump(dict(self.result_data), f, indent=4)

        # Optionally send to server
        # self.send_checked_data_to_server(dict(self.result_data), self.skipped_products["skippid"])


# --- CONFIG ---
# LWA_CLIENT_ID = "amzn1.application-oa2-client.5b8b71c8ff56492cbfe3e76508df84b9"
# LWA_CLIENT_SECRET = (
#     "amzn1.oa2-cs.v1.125f7e93012c23220035b57432b735034172c90f8adfa7e8d02c97404102dec6"
# )
# LWA_REFRESH_TOKEN = "Atzr|IwEBIIoBKW7BXRrH_RjDUHWYBtJKOwtqYxX9q5nmnuMa1xmvhkamOJGkVoDNrDoWVuHQ6ZFPGPeTJTCVigrQXOcoKniwmrkZyiFrg1chn0O0rfoi7_Rycfu6RwjgT73m-Tnf4lq60O8_gIhMrDjX-aCsKe7vI8MKMTyypijJTP6m19P5n0nzCP03RgTaRa-i_zztsWxy3cPPMLnbv0KiagmsuiXhvTv6Idp7OWkdMK6inBqTm3c6xdhRH5Qz6NvDcbiHPOJl68bvDdtDleZO9Xe_Ijw1Z29oOfRWyOqSEtNRc0nhmCXCDhwAy11gM067l_Wtfz2JwjxgthxW1oRgP29IvHig"
# SERVER_URL = "http://localhost:51483"
WAIT_TIME = 2  # seconds between actions

# Create resultData.json if not exists
if not os.path.exists("resultData.json"):
    with open("resultData.json", "w", encoding="utf-8") as f:
        json.dump({}, f, indent=4)


def main():
    checker = AmazonProductChecker(
        client_id=LWA_CLIENT_ID,
        client_secret=LWA_CLIENT_SECRET,
        refresh_token=LWA_REFRESH_TOKEN,
        server_url=SERVER_URL,
        wait_time=WAIT_TIME,
    )

    # search_keys = checker.fetch_search_keys_from_server()
    search_keys = [
     "YUJO Anti-Reflective Reading Glasses - Custom Lenses for Myopia & Hyperopia",
"9Hongching Elegant Eyeglasses Chain with Crystal Beads for Stylish Hold",
"Stylish Eyeglasses Chain with Heart & Crystal Charms - 75CM Eyewear Retainer",
"9Hongching Round Crystal Flower Eyeglasses Chain - Stylish Eyewear Holder",
"Ralferty Cat Eye Sunglasses with UV400 Protection for Stylish Sun Protection",
"Mimiyou TR90 Frames with UV400 & Anti Blue Light Protection",
"RMM Futuristic Narrow Visor Sunglasses with Mirrored Lenses for Style",
"ZENOTTIC Polarized Sunglasses with UV400 Protection for Outdoor Activities",
"Portable Candy Colour Contact Lens Box with Mirror for Easy Travel Storage",
"Contact Lens Accessories - Compact Design & Easy Maintenance",
"Compact Contact Lens Travel Kit with Mirror - Easy Carry Lens Container",
"VIAHDA UV400 Cycling Sunglasses - Large Frame for Outdoor Sports",
"MOSOSOT Vintage Acetate Eyeglasses Frames for Myopia – Luxury Round Design",
"Silicone Ear Hooks for Glasses - Non-Slip, Comfortable Support - 10 Pairs",
"MOSOSOT Vintage Acetate Reading Glasses with Clear Lenses - Stylish Eyewear",
"KLASSNUM Retro Punk UV400 Sunglasses for Outdoor Activities - Fashionable Eyewear",
"NICESEEM Laser Protective Goggles - Full Protection for IPL & Hair Removal",
"KDEAM Polarized Outdoor Sunglasses - UV Protection & Fashionable Design",
"ZUIDID Stylish Anti-UV Sunglasses with High-Definition Lenses",
"Veithdia Polarized Vintage Sunglasses for Outdoor Sports & Driving",
"KLASSNUM Polarised Clip-On Sunglasses - Anti-Glare & UV400 Protection",
"NICESEEM Anti-Fog Safety Goggles with UV Protection for Industrial Use",
"Sighttoo Rimless Foam Reading Glasses +1 +2 with Portable Case",
"EnzoDate Metal Round Frame Reading Glasses +1.0 to +3.5 - Portable Style",
"ShangeWFJia Stylish Oval Rimless Sunglasses with UV400 Protection",
"ZUIDID Punk Sunglasses UV400 Protection Stylish Fashion Eyewear",
"NICESEEM Laser Protective Goggles - OD4 Safety for IPL & Medical Laser Use",
"NICESEEM Laser Protective Goggles - Full Eye Protection for IPL & Laser Use",
"NICESEEM Anti-Fog Safety Goggles with UV Protection for Industrial Use",
"Cxbfg Face Slimming Strap - Breathable V-Face Bandage for Skin Care",
"Yangna Stainless Steel Tattoo Ink Cup Holder - Durable Body Art Accessory",
"COXO Universal Coupler Compatibility for Dental Equipment - CE Certified",
"Silicone Metatarsal Pads - Comfort & Pain Relief for Foot Care",
"Pain Relief Silicone Forefoot Pads for Hallux Valgus - Comfortable Foot Care",
"EYY High-Speed LED Dental Handpiece with Ceramic Bearings for Precision Care",
"EYYMDCL High Speed Handpiece with 3-Point Spray for Efficient Dentistry",
"GEEKHOM Lumbar Support Belt - Immediate Relief from Back Pain, Sciatica, Herniated Disc - Breathable Brace With Lumbar - Adjustable Lower Back Waist Brace - For Men & Women Healthcare Tool Sporty Cont",
"GEEKHOM Copper Knee Braces with Strap for Knee Pain Women and Men(2 Pack), Knee Compression Sleeve for Arthritis, ACL, Meniscus Tear, Joint Pain Relief, Knee Support for Working, Running",
"vidaXL Sauna Bucket and Ladle Set Solid Wood Pine",
"vidaXL Sauna Headrest Solid Wood Pine",
"XaYbZc Microfiber Glasses Bag Set - Stylish & Durable Eyewear Cases",
"Protective Glasses Case - Portable Multi-Functional Eyewear Storage Box",
"Soft PU Leather Eyewear Case - Protective & Compact Sunglasses Pouch",
"Meling Q10 Hearing Aids - Adjustable Mini Ear Amplifier for Enhanced Hearing",
"SINOCARE Safe-Accu 2 Blood Glucose Monitoring System - Accurate & Portable",
"Sinocare Safe AQ Smart Blood Glucose Test Strips for Easy Monitoring",
"Lescolton Picosecond Pen – Safe Tattoo & Blemish Removal Laser Device",
"AZDENT LED Fiber Optic Handpieces - High Speed, Reliable Dental Solutions",
"HearingUnion Mini Invisible Rechargeable Hearing Aid for Improved Sound",
"Cofoe Automatic Blood Pressure Monitor with Voice Alert for Easy Health Tracking",
"Gel Finger Protectors - Reusable & Comfortable Protection for Daily Use",
"Pedifix Toe Straightener Pad Set - Effective Hammer Toe Correction Tool",
"Toe Separator & Bunion Straightener for Foot Pain Relief - Orthopedic Tool",
"EYYMDCL High Speed LED Dental Handpiece - Low Noise & Powerful Performance",
"YUSENDENT High Speed Handpiece with LED Light for Enhanced Visibility",
"eelhoe Facial Shaping Mask - Lift Contours & Enhance Appearance",
"AZDENT Super Sonic Dental Air Scaler Handpiece - High Performance Tool",
"TRUE STAR Portable Eyebrow Ruler Caliper for Perfect Measurements",
"vidaXL Spa Surround 273x53 cm Solid Acacia Wood",
"The Skin Kitchen Natural Hydrating Body Lotion, Fragrance-Free - 150ml",
"Anti Aging and Wrinkles Microcurrent Facial Device, Boost Skin Care Products Absorption - White",
"SMS Audio Bio Sport Earbud with Heart Monitor[Black/Grey]",
"Knee Compression Sleeve, Extra Large - Black",
"Proverb Life Fuelled Skin Care Skin Definition Facial Scrub for Men, 100ml",
"Recyclable Sonic HX Replacement Toothbrush Heads",
"2 in 1 Portable Nano Mist Sprayer Handheld - Rose Gold",
"Reed Diffuser Oil Based 100ml",
"3Pcs Nail Clipper 3Pcs Tweezer 1Pc Eyelash Curler Rose Gold Professional Styling",
"Aquarius LCD Writer 8.5 Inch Ultra-Bright, Sturdy and Durable ABS, Black",
"Proverb Pro Moisturiser Life Fuelled Skin Care Hydration for Men, 50ml",
"Recyclable Oral b head replacement toothbrush",
"3′x 4′x1/2\" Beauty Salon Square Anti-fatigue Salon Mat (Foreign Party Internal Party) Black",
"vidaXL Sauna Stones 30kg",
"Aquarius Orthopedic Foot Bunion Corrector and Straightener",
"Doodle A4 Ultra-Thin Portable LED Tracing Pad with USB Cable, Dinosaur",
"Flo Neoprene Shoulder Support Strap Or Copper Unisex Relief Compression Sleeve",
"Anti Pollution Washable Cotton Mouth Mask with Valve Replaceable Filter, Black[1x Mask with 2 Filters]",
"Knee Compression Sleeve, Large - Black",
"Sighttoo Ultra-Thin TR90 Reading Glasses with Magnetic Case - Stylish & Portable",
"NONOR 93% Blue Light Blocking Clip-On Glasses for Computer & Gaming",
"Trendy Anti Blue Light Polygon Eyewear - Stylish Optical Glasses",
"DIXSG UV400 Polarised Sunglasses - Stylish Protection for Outdoor Sports",
"BARCUR Polarised Round Sunglasses - UV400 Protection for Daily Wear",
"CCspace Vintage Square Sunglasses UV400 Protection Fashion Eyewear",
"NINJONA Polarised UV400 Sunglasses - Stylish & Functional Eyewear Set",
"Peekaboo TR90 Polarized Sunglasses - Retro Style UV400 Protection",
"Double-Sided Stainless Steel Foot File - Precise Callus Remover Tool",
"eelhoe Anti-Wrinkle Patch - Reusable & Comfortable Skin Treatment",
"Protecting Hand Cream, unscented 50ml",
"100% Recyclable Replacement Toothbrush Heads for ( Sonic )",
"100% Recyclable Replacement Toothbrush Heads for ( Oral b )",
"May Flower Portable Reading Glasses - Ultra-Light Metal Frame",
"MuseLife Microfiber Cleaning Cloths – Pack of 10 for Spectacles & Sunglasses",
"BARCUR Oversize TR90 Sunglasses with UV400 Protection | Polarised Shades",
"Sonsat Polarised Sunglasses - UV400 Protection - Stylish Rectangle Design",
"Kachawoo TR90 Polarised Sunglasses - Retro Style Summer Shades",
"BARCUR Rectangle Polarised UV400 Sunglasses for Outdoor Sports",
"JNPCXI Acrylic Eyewear Chains - Durable & Stylish Accessory for Glasses",
"CCspace Vintage Round Acetate Eyeglasses Frame | Luxury Optical Eyewear",
"Microfiber Cleaning Wipes for Glasses & Lenses - Scratch-Free Care",
"NINJONA Polarised Sunglasses Set - Stylish UV Protection for Everyday Wear",
"BARCUR HD Polarized Sunscreen Sunglasses - Trendy Eye Protection",
"KACHAWOO Rimless Vintage Sunglasses with UV400 Lens for Outdoor Style",
"ZUIDID Premium UV400 Mirror Oval Sunglasses - Trendy Fashion Eyewear",
"KACHAWOO Polarized Sunglasses - UV400 Protection - Trendy Eyewear",
"Silicone Eyeglass Earhooks - Anti-Slip Design for Secure Fit - 20-100pcs",
"Veithdia Polarized UV400 Retro Sunglasses - Vintage Square Eyewear",
"LAURINNY Luxury UV400 Rectangle Sunglasses with Trendy Design",
"BOYSEEN Stylish UV400 Sunglasses with Gradient Lenses - Fashion Eyewear",
"Caterside Retro Circular Sunglasses with UV400 Protection for Fashionable Eyewear",
"Caterside Trendy Rectangular Sunglasses with UV400 Protection for Outdoor Use",
"DearBeauty Electric Cupping & Massage Device for Relaxation & Fat Burning",
"JYouCare BP-002 Automatic Blood Pressure Monitor with LCD Display",
"Ms.Dear VE Sport Body Shaping Fat Burner Massage Machine for Slimming",
"CAMMUO EMS Body Shaping Fitness Equipment for Effective Weight Loss",
"YuWell YF-02 CPAP Mask - Comfortable Fit for Sleep Apnea Relief",
"Toe Corrector Splint - Pain Relief & Support for Injured Toes",
"Natural Shampoo bar",
"Shaving Soap",
"Natural Soap Vegan 85g bar",
"Bath Salts Relaxing blend",
"Natural Deodorant",
"Natural Massage wax",
"Aras Trendy Retro Hexagon Sunglasses – UV400 Protection & Stylish Eyewear",
"Sighttoo Folding Reading Glasses - Portable & Stylish Eyewear Options",
"Trendy Square Anti Blue Light Glasses - Metal Frame Polygon Eyewear",
"RMM Trendy Square Metal Frame Reading Glasses - Fashionable Eyewear",
"Curtain Bifocal Reading Glasses Lenses - Comfortable Vision Aid",
"RMM Luxury Cat Eye Sunglasses with Mirror Lenses for Outdoor Fashion",
"MERALL Jade Gua Sha Massager - Natural Stone Facial Tool for Holistic Wellness",
"Baistra Dental Low Speed Contra Angle Handpiece - 20,000rpm Polishing Tool",
"AZDENT Dental LED Handpiece with E-generator & Shadowless Lighting",

    ]

    print(f"Found {len(search_keys)} search keys to check on Amazon.")
    checker.process_titles(search_keys)


if __name__ == "__main__":
    print("Checking un-gated products on Amazon...")
    main()

