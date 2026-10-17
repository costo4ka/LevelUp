# Credits and licenses: character sprites

Everything in `m/` and `w/` is derived from the **Universal LPC Spritesheet Character Generator**
(https://github.com/LiberatedPixelCup/Universal-LPC-Spritesheet-Character-Generator,
commit `9bf06be193b053db256b2536824af426de046aa2`): the artwork of the Liberated Pixel Cup (LPC) community.
Each PNG is a single 64x64 frame (walk animation, standing, facing the viewer) cut out of an LPC
spritesheet and recolored by swapping palette entries. Nothing was scaled or redrawn. Layers are
produced by `tools/build_character.py`; the list of items below is generated from the `credits`
entries of the LPC sheet definitions.

## License summary

LPC items are multi-licensed: for each item you may choose any of the licenses it offers.

- **Attribution is mandatory** for every item except CC0. Keep this file with the sprites, show the
  authors (or a link to this file) in the app's credits/about screen, link the licenses, and state
  that the images were changed (cropped to one frame and recolored).
- **Share-alike** (CC-BY-SA 3.0 and GPL 3.0): if you redistribute these PNGs, or a modified/composed
  version of them, you must license them under the same license (CC-BY-SA 3.0 or GPL 3.0) and keep the
  attribution. Items that only offer CC-BY-SA / GPL are the ones this applies to: Bedhead, Collared coat, Collared/Formal Longsleeve, Cowlick tall, Messy1, Necktie, Parted, Round Glasses.
  The licenses cover the artwork, not the application code that loads the PNGs.
- **OGA-BY 3.0 / CC-BY 3.0+**: attribution only, no share-alike. **CC0**: no conditions, credit is courtesy.
- Practical rule for redistribution: ship the whole `character/` folder under **CC-BY-SA 3.0** with this
  file; that satisfies every item below. (This is a summary, not legal advice.)

License texts: [CC0](https://creativecommons.org/publicdomain/zero/1.0/), [CC-BY 3.0+](https://creativecommons.org/licenses/by/3.0/), [CC-BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/), [OGA-BY 3.0](https://opengameart.org/content/oga-by-30-faq), [GPL 3.0](https://www.gnu.org/licenses/gpl-3.0.html).

Our own changes: choice of items, recolors (the custom palettes are defined in `tools/build_character.py`),
crop to the 64x64 standing frame, splitting into layers, `character.json`.

## Items at a glance

| LPC item | Our layer ids | Licenses offered | Applied |
|---|---|---|---|
| Bangs bun | hair_4 (w) | CC0 | CC0 |
| Basic Shoes | shoes | OGA-BY 3.0, CC-BY-SA 3.0, GPL 3.0 | OGA-BY 3.0 |
| Bedhead | hair_1 (w), hair_2 (m) | CC-BY-SA 3.0, GPL 3.0 | CC-BY-SA 3.0 |
| Bob | hair_2 (w) | CC0 | CC0 |
| Body Color | body | OGA-BY 3.0, CC-BY-SA 3.0, GPL 3.0 | OGA-BY 3.0 |
| Cardigan | blazer (w) | OGA-BY 3.0 | OGA-BY 3.0 |
| Collared coat | blazer (m) | CC-BY-SA 3.0, GPL 3.0 | CC-BY-SA 3.0 |
| Collared/Formal Longsleeve | shirt (m) | CC-BY-SA 3.0, GPL 3.0 | CC-BY-SA 3.0 |
| Cowlick | hair_4 (m) | CC0 | CC0 |
| Cowlick tall | hair_5 (m) | CC-BY-SA 3.0 | CC-BY-SA 3.0 |
| Cuffs | wristbands | OGA-BY 3.0 | OGA-BY 3.0 |
| Formal Pants | trousers | OGA-BY 3.0, CC-BY-SA 3.0, GPL 3.0 | OGA-BY 3.0 |
| Human Female | head (w) | OGA-BY 3.0, CC-BY-SA 3.0, GPL 3.0 | OGA-BY 3.0 |
| Human Male | head (m) | OGA-BY 3.0, CC-BY-SA 3.0, GPL 3.0 | OGA-BY 3.0 |
| Longsleeve blouse | shirt (w) | OGA-BY 3.0, CC-BY-SA 3.0, GPL 3.0 | OGA-BY 3.0 |
| Messy1 | hair_1 (m) | CC-BY-SA 3.0, GPL 3.0 | CC-BY-SA 3.0 |
| Necktie | tie | CC-BY-SA 3.0, GPL 3.0 | CC-BY-SA 3.0 |
| Pants | jeans | OGA-BY 3.0, GPL 3.0, CC-BY-SA 3.0 | OGA-BY 3.0 |
| Parted | hair_3 (m) | CC-BY-SA 3.0, GPL 3.0 | CC-BY-SA 3.0 |
| Princess | hair_5 (w) | OGA-BY 3.0, CC-BY-SA 3.0, GPL 3.0 | OGA-BY 3.0 |
| Revised Shoes | dress_shoes | OGA-BY 3.0, GPL 3.0 | OGA-BY 3.0 |
| Ring Charm | medal | CC0 | CC0 |
| Round Glasses | glasses | CC-BY-SA 3.0, GPL 3.0 | CC-BY-SA 3.0 |
| Sara Shoes | sneakers | OGA-BY 3.0, CC-BY 3.0+, GPL 2.0, GPL 3.0 | OGA-BY 3.0 |
| Shadow | shadow | CC0 | CC0 |
| Thick Headband | headband | OGA-BY 3.0+, CC-BY 3.0+, GPL 3.0 | OGA-BY 3.0+ |
| TShirt | tee | OGA-BY 3.0 | OGA-BY 3.0 |
| Wavy | hair_3 (w) | OGA-BY 3.0, CC-BY-SA 3.0, GPL 2.0, GPL 3.0 | OGA-BY 3.0 |

## Details

### Bangs bun
- Used as layers: `hair_4` (w)
- LPC sheet definition: `sheet_definitions/hair/braids/hair_bangs_bun.json`; sprite folders: `hair/bangs_bun/adult`
- Authors: ElizaWy, bluecarrot16
- Licenses offered: CC0; applied here: CC0
- Sources: https://opengameart.org/content/lpc-hair, https://github.com/ElizaWy/LPC/blob/main/Characters/Hair, https://opengameart.org/content/lpc-expanded-sit-run-jump-more
- Notes: Original by bluecarrot16, animated by ElizaWy.

### Basic Shoes
- Used as layers: `shoes`
- LPC sheet definition: `sheet_definitions/feet/shoes/feet_shoes_basic.json`; sprite folders: `feet/shoes/basic/male`, `feet/shoes/basic/thin`
- Authors: JaidynReiman, bluecarrot16, Johannes Sjölund (wulax), Joe White
- Licenses offered: OGA-BY 3.0, CC-BY-SA 3.0, GPL 3.0; applied here: OGA-BY 3.0
- Sources: https://opengameart.org/content/lpc-medieval-fantasy-character-sprites, http://opengameart.org/content/lpc-clothing-updates, https://opengameart.org/content/lpc-expanded-socks-shoes
- Notes: original by wulax, edited for v3 base by bluecarrot16, Jump/Sit/Emote/Run/Revised Combat by JaidynReiman; original by wulax, edited for female base by Joe White, edited for v3 base by bluecarrot16, Jump/Sit/Emote/Run/Revised Combat by JaidynReiman

### Bedhead
- Used as layers: `hair_1` (w), `hair_2` (m)
- LPC sheet definition: `sheet_definitions/hair/short/hair_bedhead.json`; sprite folders: `hair/bedhead/adult`
- Authors: JaidynReiman, Manuel Riecke (MrBeast)
- Licenses offered: CC-BY-SA 3.0, GPL 3.0; applied here: CC-BY-SA 3.0
- Sources: https://opengameart.org/content/liberated-pixel-cup-lpc-base-assets-sprites-map-tiles, https://opengameart.org/content/lpc-expanded-hair

### Bob
- Used as layers: `hair_2` (w)
- LPC sheet definition: `sheet_definitions/hair/bob/hair_bob.json`; sprite folders: `hair/bob/adult`
- Authors: ElizaWy, bluecarrot16
- Licenses offered: CC0; applied here: CC0
- Sources: https://opengameart.org/content/lpc-hair, https://github.com/ElizaWy/LPC/blob/main/Characters/Hair, https://opengameart.org/content/lpc-expanded-sit-run-jump-more
- Notes: Original by bluecarrot16. Edited and animated by ElizaWy.

### Body Color
- Used as layers: `body`
- LPC sheet definition: `sheet_definitions/body/body.json`; sprite folders: `body/bodies/male`, `body/bodies/female`
- Authors: bluecarrot16, JaidynReiman, Benjamin K. Smith (BenCreating), Evert, Eliza Wyatt (ElizaWy), TheraHedwig, MuffinElZangano, Durrani, Johannes Sjölund (wulax), Stephen Challener (Redshrike), Pierre Vigier (pvigier), ElizaWy, Matthew Krohn (makrohn)
- Licenses offered: OGA-BY 3.0, CC-BY-SA 3.0, GPL 3.0; applied here: OGA-BY 3.0
- Sources: https://opengameart.org/content/liberated-pixel-cup-lpc-base-assets-sprites-map-tiles, https://opengameart.org/content/lpc-medieval-fantasy-character-sprites, https://opengameart.org/content/lpc-male-jumping-animation-by-durrani, https://opengameart.org/content/lpc-runcycle-and-diagonal-walkcycle, https://opengameart.org/content/lpc-revised-character-basics, https://opengameart.org/content/lpc-be-seated, https://opengameart.org/content/lpc-runcycle-for-male-muscular-and-pregnant-character-bases-with-modular-heads, https://opengameart.org/content/lpc-jump-expanded, https://opengameart.org/content/lpc-character-bases, https://opengameart.org/content/lpc-ladies, https://opengameart.org/content/lpc-7-womens-shirts, https://gitlab.com/vagabondgame/lpc-characters
- Notes: see details at https://opengameart.org/content/lpc-character-bases; 'Thick' Male Revised Run/Climb by JaidynReiman (based on ElizaWy's LPC Revised); see details at https://opengameart.org/content/lpc-character-bases

### Cardigan
- Used as layers: `blazer` (w)
- LPC sheet definition: `sheet_definitions/torso/shirts/longsleeve/torso_clothes_longsleeve2_cardigan.json`; sprite folders: `torso/clothes/longsleeve/longsleeve2_cardigan/female`
- Authors: ElizaWy, JaidynReiman, Stephen Challener (Redshrike), Johannes Sjölund (wulax)
- Licenses offered: OGA-BY 3.0; applied here: OGA-BY 3.0
- Sources: http://opengameart.org/content/lpc-revised-character-basics, https://github.com/ElizaWy/LPC/tree/main/Characters/Clothing, https://opengameart.org/content/lpc-expanded-sit-run-jump-more, https://opengameart.org/content/lpc-expanded-simple-shirts
- Notes: original by ElizaWy; spellcast/thrust/shoot/hurt/male adapted from original by JaidynReiman

### Collared coat
- Used as layers: `blazer` (m)
- LPC sheet definition: `sheet_definitions/torso/jacket/torso_jacket_collared.json`; sprite folders: `torso/jacket/collared/male`
- Authors: bluecarrot16
- Licenses offered: CC-BY-SA 3.0, GPL 3.0; applied here: CC-BY-SA 3.0
- Sources: https://opengameart.org/content/lpc-gentleman, https://opengameart.org/content/lpc-pirates

### Collared/Formal Longsleeve
- Used as layers: `shirt` (m)
- LPC sheet definition: `sheet_definitions/torso/shirts/longsleeve/torso_clothes_longsleeve_formal.json`; sprite folders: `torso/clothes/longsleeve/formal/male`
- Authors: bluecarrot16, Thane Brimhall (pennomi), laetissima, Stephen Challener (Redshrike), Johannes Sjölund (wulax)
- Licenses offered: CC-BY-SA 3.0, GPL 3.0; applied here: CC-BY-SA 3.0
- Sources: https://opengameart.org/content/lpc-medieval-fantasy-character-sprites, https://opengameart.org/content/lpc-2-characters, https://opengameart.org/content/lpc-gentleman

### Cowlick
- Used as layers: `hair_4` (m)
- LPC sheet definition: `sheet_definitions/hair/short/hair_cowlick.json`; sprite folders: `hair/cowlick/adult`
- Authors: ElizaWy, bluecarrot16
- Licenses offered: CC0; applied here: CC0
- Sources: https://opengameart.org/content/lpc-hair, https://github.com/ElizaWy/LPC/blob/main/Characters/Hair, https://opengameart.org/content/lpc-expanded-sit-run-jump-more
- Notes: Original by bluecarrot16, animated by ElizaWy.

### Cowlick tall
- Used as layers: `hair_5` (m)
- LPC sheet definition: `sheet_definitions/hair/short/hair_cowlick_tall.json`; sprite folders: `hair/cowlick_tall/adult`
- Authors: Fabzy, bluecarrot16
- Licenses offered: CC-BY-SA 3.0; applied here: CC-BY-SA 3.0
- Sources: https://opengameart.org/content/the-revolution-hair, https://opengameart.org/content/lpc-hair

### Cuffs
- Used as layers: `wristbands`
- LPC sheet definition: `sheet_definitions/arms/wrists/wrists_cuffs.json`; sprite folders: `arms/wrists/cuffs/male`, `arms/wrists/cuffs/thin`
- Authors: bluecarrot16, JaidynReiman
- Licenses offered: OGA-BY 3.0; applied here: OGA-BY 3.0
- Sources: https://opengameart.org/content/lpc-pirates
- Notes: Original by bluecarrot16, climb/jump/sit/emote/run by JaidynReiman; Original by bluecarrot16, female/teen version by JaidynReiman

### Formal Pants
- Used as layers: `trousers`
- LPC sheet definition: `sheet_definitions/legs/pants/legs_formal.json`; sprite folders: `legs/formal/male`, `legs/formal/thin`
- Authors: bluecarrot16, JaidynReiman, ElizaWy, Johannes Sjölund (wulax), Stephen Challener (Redshrike)
- Licenses offered: OGA-BY 3.0, CC-BY-SA 3.0, GPL 3.0; applied here: OGA-BY 3.0
- Sources: https://opengameart.org/content/liberated-pixel-cup-lpc-base-assets-sprites-map-tiles, https://opengameart.org/content/lpc-medieval-fantasy-character-sprites, https://opengameart.org/content/lpc-2-characters, https://opengameart.org/content/lpc-gentleman, https://opengameart.org/content/lpc-expanded-pants
- Notes: Original pants by Stephen Challener (Redshrike), thrust/shoot bases by Wulax, Formal Pants by Bluecarrot16, climb/jump/run/sit/emotes/revised combat by JaidynReiman; Original pants by Stephen Challener (Redshrike), thrust/shoot bases by Wulax, Formal Pants by Bluecarrot16, Female/Thin version by JaidynReiman

### Human Female
- Used as layers: `head` (w)
- LPC sheet definition: `sheet_definitions/head/heads/human/heads_human_female.json`; sprite folders: `head/heads/human/female`
- Authors: bluecarrot16, Benjamin K. Smith (BenCreating), Stephen Challener (Redshrike)
- Licenses offered: OGA-BY 3.0, CC-BY-SA 3.0, GPL 3.0; applied here: OGA-BY 3.0
- Sources: https://opengameart.org/content/, https://opengameart.org/content/lpc-character-bases
- Notes: original head by Redshrike, tweaks by BenCreating, modular version by bluecarrot16

### Human Male
- Used as layers: `head` (m)
- LPC sheet definition: `sheet_definitions/head/heads/human/heads_human_male.json`; sprite folders: `head/heads/human/male`
- Authors: bluecarrot16, Benjamin K. Smith (BenCreating), Stephen Challener (Redshrike)
- Licenses offered: OGA-BY 3.0, CC-BY-SA 3.0, GPL 3.0; applied here: OGA-BY 3.0
- Sources: https://opengameart.org/content/liberated-pixel-cup-lpc-base-assets-sprites-map-tiles, https://opengameart.org/content/lpc-character-bases
- Notes: original head by Redshrike, tweaks by BenCreating, modular version by bluecarrot16

### Longsleeve blouse
- Used as layers: `shirt` (w)
- LPC sheet definition: `sheet_definitions/torso/shirts/torso_clothes_blouse_longsleeve.json`; sprite folders: `torso/clothes/blouse_longsleeve/female`
- Authors: bluecarrot16, ElizaWy, Lanea Zimmerman (Sharm)
- Licenses offered: OGA-BY 3.0, CC-BY-SA 3.0, GPL 3.0; applied here: OGA-BY 3.0
- Sources: https://opengameart.org/content/liberated-pixel-cup-lpc-base-assets-sprites-map-tiles, https://opengameart.org/content/lpc-7-womens-shirts
- Notes: original princess.xcf by Sharm, edited to blouse by ElizaWy; blouse + longsleeve adapted to v3 bases by bluecarrot16

### Messy1
- Used as layers: `hair_1` (m)
- LPC sheet definition: `sheet_definitions/hair/short/hair_messy1.json`; sprite folders: `hair/messy1/adult`
- Authors: JaidynReiman, Manuel Riecke (MrBeast)
- Licenses offered: CC-BY-SA 3.0, GPL 3.0; applied here: CC-BY-SA 3.0
- Sources: https://opengameart.org/content/liberated-pixel-cup-lpc-base-assets-sprites-map-tiles, https://opengameart.org/content/lpc-expanded-hair

### Necktie
- Used as layers: `tie`
- LPC sheet definition: `sheet_definitions/headwear/neck/neck_necktie.json`; sprite folders: `neck/tie/necktie/male`, `neck/tie/necktie/female`
- Authors: JaidynReiman, bluecarrot16, Thane Brimhall (pennomi), laetissima, Makrohn
- Licenses offered: CC-BY-SA 3.0, GPL 3.0; applied here: CC-BY-SA 3.0
- Sources: https://opengameart.org/content/lpc-2-characters, https://opengameart.org/content/lpc-gentleman
- Notes: Originally by pennomi/laetissima/Makrohn, edited by bluecarrot16, animations and recolors by JaidynReiman

### Pants
- Used as layers: `jeans`
- LPC sheet definition: `sheet_definitions/legs/pants/legs_pants.json`; sprite folders: `legs/pants/male`, `legs/pants/thin`
- Authors: bluecarrot16, JaidynReiman, ElizaWy, Matthew Krohn (makrohn), Johannes Sjölund (wulax), Stephen Challener (Redshrike), Joe White
- Licenses offered: OGA-BY 3.0, GPL 3.0, CC-BY-SA 3.0; applied here: OGA-BY 3.0
- Sources: https://opengameart.org/content/liberated-pixel-cup-lpc-base-assets-sprites-map-tiles, https://opengameart.org/content/lpc-medieval-fantasy-character-sprites, https://opengameart.org/content/lpc-expanded-pants, http://opengameart.org/content/lpc-clothing-updates
- Notes: original male pants by wulax, recolors and edits to v3 base by bluecarrot16, climb/jump/run/sit/emotes/revised combat by JaidynReiman based on ElizaWy's LPC Revised; original male pants by wulax, edited for female by Joe White, recolors and edits to v3 base by bluecarrot16, teen legs by ElizaWy derived from base, climb/jump/run/sit/emotes/revised combat by JaidynReiman based on ElizaWy's LPC Revised

### Parted
- Used as layers: `hair_3` (m)
- LPC sheet definition: `sheet_definitions/hair/short/hair_parted.json`; sprite folders: `hair/parted/adult`
- Authors: JaidynReiman, Joe White, Manuel Riecke (MrBeast)
- Licenses offered: CC-BY-SA 3.0, GPL 3.0; applied here: CC-BY-SA 3.0
- Sources: https://opengameart.org/content/liberated-pixel-cup-lpc-base-assets-sprites-map-tiles, https://github.com/jrconway3/Universal-LPC-spritesheet/commit/46ddcf05a0e43e7aa6ffd47d350eef0eb529ac24, https://opengameart.org/content/lpc-expanded-hair
- Notes: down 4 and 5 added by JaidynReiman; recolors by Joe White; original by Manuel Riecke (MrBeast)

### Princess
- Used as layers: `hair_5` (w)
- LPC sheet definition: `sheet_definitions/hair/xlong/hair_princess.json`; sprite folders: `hair/princess/adult/fg`, `hair/princess/adult/bg`
- Authors: JaidynReiman, Lanea Zimmerman (Sharm)
- Licenses offered: OGA-BY 3.0, CC-BY-SA 3.0, GPL 3.0; applied here: OGA-BY 3.0
- Sources: https://opengameart.org/content/liberated-pixel-cup-lpc-base-assets-sprites-map-tiles, https://opengameart.org/content/lpc-expanded-hair

### Revised Shoes
- Used as layers: `dress_shoes`
- LPC sheet definition: `sheet_definitions/feet/shoes/feet_shoes_revised.json`; sprite folders: `feet/shoes/revised/male`, `feet/shoes/revised/thin`
- Authors: JaidynReiman, ElizaWy, Bluecarrot16, Stephen Challener (Redshrike), Johannes Sjölund (wulax)
- Licenses offered: OGA-BY 3.0, GPL 3.0; applied here: OGA-BY 3.0
- Sources: https://github.com/ElizaWy/LPC/tree/main/Characters/Clothing, https://opengameart.org/content/lpc-expanded-socks-shoes, https://opengameart.org/content/lpc-expanded-sit-run-jump-more
- Notes: original overalls and shoes by ElizaWy, base animations adapted from v3 overalls by bluecarrot16, shoes by JaidynReiman; original by ElizaWy, remaining frames by JaidynReiman

### Ring Charm
- Used as layers: `medal`
- LPC sheet definition: `sheet_definitions/headwear/neck/charms/neck_charm_ring.json`; sprite folders: `neck/charm/ring/male`, `neck/charm/ring/female`
- Authors: bluecarrot16
- Licenses offered: CC0; applied here: CC0
- Sources: https://opengameart.org/content/lpc-jewelry

### Round Glasses
- Used as layers: `glasses`
- LPC sheet definition: `sheet_definitions/headwear/accessories/glasses/facial_glasses_round.json`; sprite folders: `facial/glasses/round/adult`
- Authors: bluecarrot16, Thane Brimhall (pennomi), laetissima
- Licenses offered: CC-BY-SA 3.0, GPL 3.0; applied here: CC-BY-SA 3.0
- Sources: https://opengameart.org/content/clothing-facial-features-and-ui-elements, https://opengameart.org/content/lpc-gentleman

### Sara Shoes
- Used as layers: `sneakers`
- LPC sheet definition: `sheet_definitions/feet/shoes/feet_shoes_sara.json`; sprite folders: `feet/shoes/sara/male`, `feet/shoes/sara/thin`
- Authors: JaidynReiman, Bluecarrot16, Mandi Paugh, Stephen Challener (Redshrike), William.Thompsonj
- Licenses offered: OGA-BY 3.0, CC-BY 3.0+, GPL 2.0, GPL 3.0; applied here: OGA-BY 3.0
- Sources: http://opengameart.org/content/sara-wizard, https://opengameart.org/content/lpc-sara, https://opengameart.org/content/lpc-expanded-socks-shoes
- Notes: LPC Sara by Redshrike, contributed by William Thompsonj, Shoes Separated by Bluecarrot16, Jump/Sit/Emote/Run/Revised Combat by JaidynReiman; LPC Sara by Redshrike, contributed by William Thompsonj, Shoes Separated by Bluecarrot16, Male Version and Jump/Sit/Emote/Run/Revised Combat by JaidynReiman

### Shadow
- Used as layers: `shadow`
- LPC sheet definition: `sheet_definitions/body/shadow.json`; sprite folders: `shadow/adult`
- Authors: drjamgo@hotmail.com, JaidynReiman
- Licenses offered: CC0; applied here: CC0
- Sources: https://opengameart.org/content/shadow-for-lpc-sprite
- Notes: Original by Dr. Jamgo, jump/sit/emote/run/revised combat by JaidynReiman

### Thick Headband
- Used as layers: `headband`
- LPC sheet definition: `sheet_definitions/headwear/coverings/headbands/hat_headband_thick.json`; sprite folders: `hat/headband/thick/adult`
- Authors: JaidynReiman
- Licenses offered: OGA-BY 3.0+, CC-BY 3.0+, GPL 3.0; applied here: OGA-BY 3.0+
- Sources: https://opengameart.org/content/lpc-relm-hair-xlong-ponytail, https://opengameart.org/content/lpc-expanded-hats-facial-helmets

### TShirt
- Used as layers: `tee`
- LPC sheet definition: `sheet_definitions/torso/shirts/shortsleeve/torso_clothes_tshirt.json`; sprite folders: `torso/clothes/shortsleeve/tshirt/male`, `torso/clothes/shortsleeve/tshirt/female`
- Authors: ElizaWy, JaidynReiman, Stephen Challener (Redshrike), Johannes Sjölund (wulax)
- Licenses offered: OGA-BY 3.0; applied here: OGA-BY 3.0
- Sources: https://opengameart.org/content/lpc-revised-character-basics, https://github.com/ElizaWy/LPC/tree/main/Characters/Clothing, https://opengameart.org/content/lpc-expanded-sit-run-jump-more, https://opengameart.org/content/lpc-expanded-simple-shirts
- Notes: original by ElizaWy; spellcast/thrust/shoot/hurt/male adapted from original by JaidynReiman

### Wavy
- Used as layers: `hair_3` (w)
- LPC sheet definition: `sheet_definitions/hair/long/hair_wavy.json`; sprite folders: `hair/wavy/adult/fg`, `hair/wavy/adult/bg`
- Authors: JaidynReiman, Nila122
- Licenses offered: OGA-BY 3.0, CC-BY-SA 3.0, GPL 2.0, GPL 3.0; applied here: OGA-BY 3.0
- Sources: https://opengameart.org/content/3-hairs-for-lpc, https://opengameart.org/content/lpc-expanded-hair
