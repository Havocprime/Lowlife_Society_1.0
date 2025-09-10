
# =================================
# GAME/src/assets/item_images.py
# =================================
from __future__ import annotations
from typing import Optional, Dict
from src.models.item import ItemClass

# --------------- Fill these with your Discord CDN URLs ---------------
GLOBAL_DEFAULT = "https://media.discordapp.net/attachments/1414177780920352838/1414208308494991593/9_quests.png?ex=68bebb9f&is=68bd6a1f&hm=43a1d0dbc87081d7a9d8417177f5d26a2255f0689846ba7f62b872a8d76d51ac&=&format=webp&quality=lossless&width=126&height=114"  # used if nothing else matches

CLASS_DEFAULTS: Dict[ItemClass, str] = {
    ItemClass.misc:        "https://media.discordapp.net/attachments/1414177780920352838/1414208305324097676/1_Misc.png?ex=68bebb9e&is=68bd6a1e&hm=4c99bb11446bb4d9c53a80515efb71ccf5bfcbbd667023f548a9a3b5ca125afb&=&format=webp&quality=lossless&width=108&height=119",
    ItemClass.tool:        "https://media.discordapp.net/attachments/1414177780920352838/1414208305844453449/2_tool.png?ex=68bebb9e&is=68bd6a1e&hm=3cba1d7a18aaa0539aa3a378ccaed871a1d7b8d7b8917e7b04f71622b3017f2c&=&format=webp&quality=lossless&width=118&height=123",
    ItemClass.weapon:      "https://media.discordapp.net/attachments/1414177780920352838/1414208386257391656/a_rifle.png?ex=68bebbb2&is=68bd6a32&hm=799acc1276d0ed84c2e7fc691e7639c69dac0f56605f79f8d20cef9bc5e766c8&=&format=webp&quality=lossless&width=127&height=121",
    ItemClass.gear:        "https://media.discordapp.net/attachments/1414177780920352838/1414208356775624765/a_helmets.png?ex=68bebbaa&is=68bd6a2a&hm=a2706622010f8b3748ff38f96224529a912dae681c202366510462396c50fc03&=&format=webp&quality=lossless&width=132&height=123",
    ItemClass.consumable:  "https://media.discordapp.net/attachments/1414177780920352838/1414208355609608304/a_food.png?ex=68bebbaa&is=68bd6a2a&hm=026f4f2023964e7dc2ece774b14a35d2486f37214c489d2de846d74207451af9&=&format=webp&quality=lossless&width=108&height=110",
    ItemClass.ammo:        "https://media.discordapp.net/attachments/1414177780920352838/1414208307253477417/6_ammo.png?ex=68bebb9f&is=68bd6a1f&hm=c9a1c9480db36e8fda578e586d3992036f02b5d5edcd0c04bb9df469043546ab&=&format=webp&quality=lossless&width=126&height=118",
    ItemClass.currency:    "https://media.discordapp.net/attachments/1414177780920352838/1414208415873499176/a_USD_CASH.png?ex=68bebbb9&is=68bd6a39&hm=c5d61d4932a2c848b84f33b3c88a02524eb078a407d4c9bbd2f311c46ffe4ee8&=&format=webp&quality=lossless&width=138&height=97",
    ItemClass.drugs:       "https://media.discordapp.net/attachments/1414177780920352838/1414208328053166150/a_depressant.png?ex=68bebba4&is=68bd6a24&hm=85d9d3fccffd04a9bc65b4bff7a21954bef2f48e870c7a687894bf83b9092e8a&=&format=webp&quality=lossless&width=98&height=112",
    ItemClass.quest:       "https://media.discordapp.net/attachments/1414177780920352838/1414208308494991593/9_quests.png?ex=68bebb9f&is=68bd6a1f&hm=43a1d0dbc87081d7a9d8417177f5d26a2255f0689846ba7f62b872a8d76d51ac&=&format=webp&quality=lossless&width=126&height=114",
    ItemClass.junk:        "https://media.discordapp.net/attachments/1414177780920352838/1414208309069877329/10_junk.png?ex=68bebb9f&is=68bd6a1f&hm=1dce0ba1e085779c9acc0ae4f9a187644b1bb8a59ad430b3b2d299024c48d611&=&format=webp&quality=lossless&width=118&height=119",
}

# Keys must match the canonical subcategory labels from your model:
# WeaponSub: Melee, Pistol, Revolver, SMG, Shotgun, Rifle, Sniper, Thrown, Tool
# GearSub: Clothing, Armor, Vest, ChestRig, Helmet, Face, Backpack, Utility
# ConsumableSub: Food, Drink, Medical, Other
# AmmoSub: Pistol, Rifle, Shotgun, Other
# DrugsSub: Depressant, Stimulant, Hallucinogen, Dissociative, Narcotic, Inhalant
# Currency: USD, $, Cash, Bitcoin, BTC, Crypto
SUBCATEGORY_IMAGES: Dict[ItemClass, Dict[str, str]] = {
    ItemClass.weapon: {
        "Melee":    "https://media.discordapp.net/attachments/1414177780920352838/1414208358101160048/a_melee.png?ex=68bebbab&is=68bd6a2b&hm=e627fb2deb0b72acacbeb9e4ad3d6d0a76f223795bdc6c40395ff14966b2e81c&=&format=webp&quality=lossless&width=126&height=120",
        "Pistol":   "https://media.discordapp.net/attachments/1414177780920352838/1414208385100021871/a_pistol.png?ex=68bebbb1&is=68bd6a31&hm=730a05b8a4dcfcadf2245198f1d6f6bcd3cef0ed7df51c7412595bfaf623e5e7&=&format=webp&quality=lossless&width=135&height=114",
        "Revolver": "https://media.discordapp.net/attachments/1414177780920352838/1414208385905328178/a_revolver.png?ex=68bebbb1&is=68bd6a31&hm=d99b686ca2adf5cf25a3330f0a35ca2427ee30b859b7f90eed3b509e3f0fa158&=&format=webp&quality=lossless&width=129&height=98",
        "SMG":      "https://media.discordapp.net/attachments/1414177780920352838/1414208388518121583/a_smg.png?ex=68bebbb2&is=68bd6a32&hm=cf315a15de7c5dd439502308c5e0ee8c7b6241e5777b07b2728e1ee6374ac2c3&=&format=webp&quality=lossless&width=138&height=108",
        "Shotgun":  "https://media.discordapp.net/attachments/1414177780920352838/1414208387486449714/a_shotgun.png?ex=68bebbb2&is=68bd6a32&hm=f0fb49e3205f98a0eb0fde6f94bb1b7ddfdcd7a82f9447e21b9ffd676e63f426&=&format=webp&quality=lossless&width=133&height=134",
        "Rifle":    "https://media.discordapp.net/attachments/1414177780920352838/1414208386257391656/a_rifle.png?ex=68bebbb2&is=68bd6a32&hm=799acc1276d0ed84c2e7fc691e7639c69dac0f56605f79f8d20cef9bc5e766c8&=&format=webp&quality=lossless&width=127&height=121",
        "Sniper":   "https://media.discordapp.net/attachments/1414177780920352838/1414208388954591262/a_sniper.png?ex=68bebbb2&is=68bd6a32&hm=46633c6f7699f6dca42a76370045b28ee92ba476d46ee83c994d68eae64cdf86&=&format=webp&quality=lossless&width=132&height=142",
        "Thrown":   "https://media.discordapp.net/attachments/1414177780920352838/1414208415160467508/a_thrown.png?ex=68bebbb8&is=68bd6a38&hm=06cf7a6cfe179cfa16f774be3f9d567e0d27d8d2c8c4be23120ea807230f9e92&=&format=webp&quality=lossless&width=134&height=134",
        "Tool":     "https://media.discordapp.net/attachments/1414177780920352838/1414208415550541864/a_tool.png?ex=68bebbb8&is=68bd6a38&hm=41482480d472d43edc28ce2e005de71427e590d31b25703fe462b7a3c1d85fe7&=&format=webp&quality=lossless&width=132&height=128",
    },
    ItemClass.gear: {
        "Clothing": "https://media.discordapp.net/attachments/1414177780920352838/1414208327738462271/a_clothing.png?ex=68bebba4&is=68bd6a24&hm=b0a67a2e0a1382334fc2bfa25b0d5f88b5bf097314f58f14cd5c518a79ed452b&=&format=webp&quality=lossless&width=146&height=136",
        "Armor":    "https://media.discordapp.net/attachments/1414177780920352838/1414208326090231808/a_armor.png?ex=68bebba3&is=68bd6a23&hm=3af79bf1d48e6da72920c70893a7821ae541e0470f559044d7a13debca3c4bdd&=&format=webp&quality=lossless&width=117&height=126",
        "Vest":     "https://media.discordapp.net/attachments/1414177780920352838/1414208327373553674/a_chestrig.png?ex=68bebba3&is=68bd6a23&hm=9d729a02d5221f002dd7971538a0af0b24d5cd279f1a5b099d0cd2957cd62e03&=&format=webp&quality=lossless&width=128&height=120",
        "ChestRig": "https://media.discordapp.net/attachments/1414177780920352838/1414208327373553674/a_chestrig.png?ex=68bebba3&is=68bd6a23&hm=9d729a02d5221f002dd7971538a0af0b24d5cd279f1a5b099d0cd2957cd62e03&=&format=webp&quality=lossless&width=128&height=120",
        "Helmet":   "https://media.discordapp.net/attachments/1414177780920352838/1414208356775624765/a_helmets.png?ex=68bebbaa&is=68bd6a2a&hm=a2706622010f8b3748ff38f96224529a912dae681c202366510462396c50fc03&=&format=webp&quality=lossless&width=132&height=123",
        "Face":     "https://media.discordapp.net/attachments/1414177780920352838/1414208329504391168/a_facemask.png?ex=68bebba4&is=68bd6a24&hm=62b05577856675f019b79cf906637b517e4c9f79f15659f12711ce6dd2d42388&=&format=webp&quality=lossless&width=119&height=126",
        "Backpack": "https://media.discordapp.net/attachments/1414177780920352838/1414208326518046740/a_backpack.png?ex=68bebba3&is=68bd6a23&hm=60b69ac284596ee1f3aa4c91e8896fa6d8fd7f073c3735d277544255a55c118e&=&format=webp&quality=lossless&width=118&height=120",
        "Utility":  "https://media.discordapp.net/attachments/1414177780920352838/1414208305844453449/2_tool.png?ex=68bebb9e&is=68bd6a1e&hm=3cba1d7a18aaa0539aa3a378ccaed871a1d7b8d7b8917e7b04f71622b3017f2c&=&format=webp&quality=lossless&width=118&height=123",
    },
    ItemClass.consumable: {
        "Food":     "https://media.discordapp.net/attachments/1414177780920352838/1414208355609608304/a_food.png?ex=68bebbaa&is=68bd6a2a&hm=026f4f2023964e7dc2ece774b14a35d2486f37214c489d2de846d74207451af9&=&format=webp&quality=lossless&width=108&height=110",
        "Drink":    "https://media.discordapp.net/attachments/1414177780920352838/1414208328984428595/a_drink.png?ex=68bebba4&is=68bd6a24&hm=b905869d078050719a74320b563930c0e07c49aaeab03ca31acdd4ab7fb0ae86&=&format=webp&quality=lossless&width=100&height=123",
        "Medical":  "https://media.discordapp.net/attachments/1414177780920352838/1414208357648040036/a_medical.png?ex=68bebbab&is=68bd6a2b&hm=e2589ce245f011eaa4697ff4871d3e51da02239997e17ad81e8c23a4ca60eb68&=&format=webp&quality=lossless&width=118&height=122",
        "Other":    "https://media.discordapp.net/attachments/1414177780920352838/1414208359074234419/a_other.png?ex=68bebbab&is=68bd6a2b&hm=335f2406112e60abd17b3787448eff74181d15f6e2fc5876c09ed9048bc9fc1b&=&format=webp&quality=lossless&width=110&height=115",
    },
    ItemClass.ammo: {
        "Pistol":   "https://media.discordapp.net/attachments/1414177780920352838/1414208385569652839/a_pistol_ammo.png?ex=68bebbb1&is=68bd6a31&hm=60f145def147ec9a62f65078ede191905ec612529c498ff8a3b7e95f56c03875&=&format=webp&quality=lossless&width=37&height=68",
        "Rifle":    "https://media.discordapp.net/attachments/1414177780920352838/1414208386823884890/a_rifle_ammo.png?ex=68bebbb2&is=68bd6a32&hm=a2be7f2b65e96ced50c9ac02ef44e7f3a7a33d0c23da45b4975c4e6e4ed34bab&=&format=webp&quality=lossless&width=34&height=92",
        "Shotgun":  "https://media.discordapp.net/attachments/1414177780920352838/1414208387486449714/a_shotgun.png?ex=68bebbb2&is=68bd6a32&hm=f0fb49e3205f98a0eb0fde6f94bb1b7ddfdcd7a82f9447e21b9ffd676e63f426&=&format=webp&quality=lossless&width=133&height=134",
        "Other":    "https://media.discordapp.net/attachments/1414177780920352838/1414208359581614201/a_other_ammo.png?ex=68bebbab&is=68bd6a2b&hm=5c5619b177e3737d5c022debf9481c74cf11ae5d930379cd09ca5d0b7fbb7905&=&format=webp&quality=lossless&width=102&height=110",
    },
    ItemClass.currency: {
        "USD":      "https://media.discordapp.net/attachments/1414177780920352838/1414208307748540586/7_currency.png?ex=68bebb9f&is=68bd6a1f&hm=7fff3cc017af7695aa7347e108b8022765d22b989fdf9d2b622656c49af93b2c&=&format=webp&quality=lossless&width=154&height=110",
        "$":        "https://media.discordapp.net/attachments/1414177780920352838/1414208307748540586/7_currency.png?ex=68bebb9f&is=68bd6a1f&hm=7fff3cc017af7695aa7347e108b8022765d22b989fdf9d2b622656c49af93b2c&=&format=webp&quality=lossless&width=154&height=110",
        "Cash":     "https://media.discordapp.net/attachments/1414177780920352838/1414208307748540586/7_currency.png?ex=68bebb9f&is=68bd6a1f&hm=7fff3cc017af7695aa7347e108b8022765d22b989fdf9d2b622656c49af93b2c&=&format=webp&quality=lossless&width=154&height=110",
        "Bitcoin":  "https://media.discordapp.net/attachments/1414177780920352838/1414208326979424288/a_Bitcoin.png?ex=68bebba3&is=68bd6a23&hm=b4406dca6028a5aec7caa8d1a84975a31eb72058d41c24083181fa1ada430058&=&format=webp&quality=lossless&width=122&height=127",
        "BTC":      "https://media.discordapp.net/attachments/1414177780920352838/1414208326979424288/a_Bitcoin.png?ex=68bebba3&is=68bd6a23&hm=b4406dca6028a5aec7caa8d1a84975a31eb72058d41c24083181fa1ada430058&=&format=webp&quality=lossless&width=122&height=127",
        "Crypto":   "https://media.discordapp.net/attachments/1414177780920352838/1414208326979424288/a_Bitcoin.png?ex=68bebba3&is=68bd6a23&hm=b4406dca6028a5aec7caa8d1a84975a31eb72058d41c24083181fa1ada430058&=&format=webp&quality=lossless&width=122&height=127",
    },
    ItemClass.drugs: {
        "Depressant":   "https://media.discordapp.net/attachments/1414177780920352838/1414208328422133852/a_dissociative.png?ex=68bebba4&is=68bd6a24&hm=c441edc18bf93b79d6e39618f04b83916c39763b9091e434909d4f6f6b2e5278&=&format=webp&quality=lossless&width=105&height=122",
        "Stimulant":    "https://media.discordapp.net/attachments/1414177780920352838/1414208414812209254/a_stimulant.png?ex=68bebbb8&is=68bd6a38&hm=2471d2deda51273c82fd45c60dcdd56faaac15648342ae9c3b2f5e639d7e2338&=&format=webp&quality=lossless&width=122&height=130",
        "Hallucinogen": "https://media.discordapp.net/attachments/1414177780920352838/1414208356289216553/a_hallucinogen.png?ex=68bebbaa&is=68bd6a2a&hm=6ba4258361264fa5eeef10030b874680cf8bbaf34278711f13d3802eed7a64c7&=&format=webp&quality=lossless&width=122&height=122",
        "Dissociative": "https://media.discordapp.net/attachments/1414177780920352838/1414208358495289434/a_narcotic.png?ex=68bebbab&is=68bd6a2b&hm=1e6649bb3eeb92bd3d4de9da9520140c1fefd827a95246592b26db938f42db50&=&format=webp&quality=lossless&width=86&height=123",
        "Narcotic":     "https://media.discordapp.net/attachments/1414177780920352838/1414208328053166150/a_depressant.png?ex=68bebba4&is=68bd6a24&hm=85d9d3fccffd04a9bc65b4bff7a21954bef2f48e870c7a687894bf83b9092e8a&=&format=webp&quality=lossless&width=98&height=112",
        "Inhalant":     "https://media.discordapp.net/attachments/1414177780920352838/1414208357178282004/a_inhalant.png?ex=68bebbab&is=68bd6a2b&hm=8937015cd2cc029c97bdb86de433877d128612951a6eb57f0813565fc7efffd2&=&format=webp&quality=lossless&width=123&height=117",
    },
}

# --------------- Lookup ---------------
def item_image_for(item_class: ItemClass, subcategory: Optional[str] = None) -> Optional[str]:
    """
    Return a CDN URL for the given item class/subcategory.
    - Tries subcategory first (case-insensitive match against keys above)
    - Then class default
    - Then global default
    """
    # Subcategory (case-insensitive)
    if subcategory:
        sub_map = SUBCATEGORY_IMAGES.get(item_class, {})
        url = sub_map.get(str(subcategory))
        if url:
            return url
        sub_cf = str(subcategory).casefold()
        for k, v in sub_map.items():
            if str(k).casefold() == sub_cf:
                return v

    # Class default
    url = CLASS_DEFAULTS.get(item_class)
    if url:
        return url

    # Global default
    return GLOBAL_DEFAULT or None
