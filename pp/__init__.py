from common.constants import gameModes

from pp import ez_peace, ez_rosu_pp

PP_CALCULATORS = {
    gameModes.STD: ez_rosu_pp.EzRosu,
    gameModes.TAIKO: ez_rosu_pp.EzRosu,
    gameModes.CTB: ez_rosu_pp.EzRosu,
    gameModes.MANIA: ez_rosu_pp.EzRosu
}

PP_RELAX_CALCULATORS = {
    gameModes.STD: ez_peace.EzPeace,
    gameModes.TAIKO: ez_peace.EzPeace,
    gameModes.CTB: ez_peace.EzPeace
}
PP_AUTO_CALCULATORS = {
    gameModes.STD: ez_peace.EzPeace,
}