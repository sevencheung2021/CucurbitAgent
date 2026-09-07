"""Genome catalog from v28 GENOME_DIR_MAP."""

GENOME_DIR_MAP = {
    "🍉 Watermelon (Citrullus lanatus)": {
        "97103": {"v1.0": "watermelon/97103/v1", "v2.0": "watermelon/97103/v2", "v2.5": "watermelon/97103/v2.5"},
        "Cordophanus": {"v1.5": "watermelon/cordophanus/v1.5", "v2.0": "watermelon/cordophanus/v2"},
        "PI537277": {"v1.0": "watermelon/PI537277"},
        "USVL246": {"v1.0": "watermelon/USVL246"},
        "USVL531": {"v1.0": "watermelon/USVL531"},
        "WCG (Charleston Gray)": {"v1.0": "watermelon/WCG/v1", "v2.0": "watermelon/WCG/v2", "v2.5": "watermelon/WCG/v2.5"},
    },
    "🥒 Cucumber (Cucumis sativus)": {
        "Chinese Long": {"v1.0": "cucumber/Chinese_long/v1", "v2.0": "cucumber/Chinese_long/v2", "v3.0": "cucumber/Chinese_long/v3"},
        "Gy14": {"v1.0": "cucumber/Gy14/v1", "v2.0": "cucumber/Gy14/v2", "v2.1": "cucumber/Gy14/v2.1"},
        "B10": {"v3.0": "cucumber/B10"},
        "C. hystrix": {"v1.0": "cucumber/C_hystrix"},
        "PI183967 (Hardwickii)": {"v1.0": "cucumber/PI183967"},
    },
    "🍈 Melon (Cucumis melo)": {
        "DHL92": {"v3.5.1": "melon/DHL92/v3.5.1", "v3.6.1": "melon/DHL92/v3.6.1", "v4.0": "melon/DHL92/v4.0"},
        "Charmono": {"v1.1": "melon/Charmono"},
        "Harukei3": {"v1.41": "melon/Harukei3"},
        "IVF77": {"v1.0": "melon/IVF77"},
        "Payzawat": {"v1.0": "melon/Payzawat"},
        "PI482460": {"v1.0": "melon/PI482460"},
    },
    "🎃 Pumpkin & Squash (Cucurbita)": {
        "C. maxima": {"v1.0": "Cucurbita_maxima/v1", "v1.1": "Cucurbita_maxima/v1.1", "v2.0": "Cucurbita_maxima/v2"},
        "C. moschata": {"v1.0": "Cucurbita_moschata/v1", "v2.0": "Cucurbita_moschata/v2"},
        "C. pepo (C39)": {"v1.0": "Cucurbita_pepo/C39"},
        "C. pepo (MU-CU-16)": {"v4.1": "Cucurbita_pepo/MU-CU-16"},
        "C. argyrosperma": {"v1.0": "Cucurbita_argyrosperma/argyrosperma/v1", "v2.0": "Cucurbita_argyrosperma/argyrosperma/v2"},
        "C. sororia": {"v1.0": "Cucurbita_argyrosperma/sororia"},
    },
    "🥒 Bitter Gourd (Momordica charantia)": {
        "Dali-11": {"v1.0": "BitterGourd/Dali-11"},
        "OHB3-1": {"v2.0": "BitterGourd/OHB3-1"},
        "TR": {"v1.0": "BitterGourd/TR"},
    },
    "🍐 Bottle Gourd (Lagenaria siceraria)": {
        "HZ": {"v2.0": "BottleGourd/HZ"},
        "USVL1VR-Ls": {"v1.0": "BottleGourd/USVL1VR-Ls"},
    },
    "🥒 Sponge Gourd (Luffa)": {
        "AG-4": {"v1.0": "SpongeGourd/AG-4"},
        "L. cylindrica": {"v1.0": "SpongeGourd/L_cylindrica"},
        "P93075": {"v1.0": "SpongeGourd/P93075"},
    },
    "🌿 Other Cucurbits": {
        "Wax Gourd (Benincasa hispida)": {"v1.0": "WaxGourd"},
        "Snake Gourd (Trichosanthes)": {"v1.0": "SnakeGourd"},
        "Chayote (Sechium edule)": {"v1.0": "chayote"},
        "Monkfruit (Siraitia grosvenorii)": {"v1.0": "monkfruit"},
    },
}

SPECIES_DIRS = {
    "Watermelon": "watermelon_pdb",
    "Cucumber": "cucumber_pdb",
    "Melon": "melon_pdb",
    "Pumpkin (C. moschata)": "pumpkin_moschata_pdb",
    "Pumpkin (C. pepo)": "pumpkin_pepo_pdb",
    "BitterGourd": "bittergourd_pdb",
    "BottleGourd": "bottlegourd_pdb",
    "WaxGourd": "waxgourd_pdb",
    "SpongeGourd": "spongegourd_pdb",
}

# GPSite roots under web_structure_dir (all_sites_json/ + optional summary CSV).
# Cucumber keeps the historical cucu_v3_pdb_site layout; Watermelon sites TBD.
SPECIES_SITE_DIRS = {
    "Watermelon": "watermelon_pdb_site",
    "Cucumber": "cucu_v3_pdb_site",
    "Melon": "melon_pdb_site",
    "Pumpkin (C. moschata)": "pumpkin_moschata_pdb_site",
    "Pumpkin (C. pepo)": "pumpkin_pepo_pdb_site",
    "BitterGourd": "bittergourd_pdb_site",
    "BottleGourd": "bottlegourd_pdb_site",
    "WaxGourd": "waxgourd_pdb_site",
    "SpongeGourd": "spongegourd_pdb_site",
}

SPECIES_GPSITE_CSV = {
    "Cucumber": "ChineseLong_v3_GPSite_Final.csv",
}
