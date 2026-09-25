from app.species.base import MODEL, SpeciesConfig
from app.species import boletus_edulis, imleria_badia, lactarius_deliciosus, suillus_luteus

SPECIES: dict[str, SpeciesConfig] = {
    c.id: c for c in (
        boletus_edulis.CONFIG, imleria_badia.CONFIG,
        suillus_luteus.CONFIG, lactarius_deliciosus.CONFIG,
    )
}

__all__ = ["MODEL", "SPECIES", "SpeciesConfig"]
