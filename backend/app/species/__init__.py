from app.species.base import MODEL, SpeciesConfig
from app.species import (
    armillaria_mellea, boletus_edulis, boletus_reticulatus, cantharellus_cibarius,
    imleria_badia, lactarius_deliciosus, leccinum_aurantiacum, leccinum_scabrum,
    macrolepiota_procera, suillus_luteus,
)

# 10 popular edible forest mushrooms of Poland (order = order in the UI)
SPECIES: dict[str, SpeciesConfig] = {
    c.id: c for c in (
        boletus_edulis.CONFIG, imleria_badia.CONFIG, cantharellus_cibarius.CONFIG,
        suillus_luteus.CONFIG, lactarius_deliciosus.CONFIG, macrolepiota_procera.CONFIG,
        leccinum_scabrum.CONFIG, leccinum_aurantiacum.CONFIG, armillaria_mellea.CONFIG,
        boletus_reticulatus.CONFIG,
    )
}

__all__ = ["MODEL", "SPECIES", "SpeciesConfig"]
