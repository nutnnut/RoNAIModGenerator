"""Turns the handful of choices the app shows into a full generator config.

Everything the UI can express is defined here, so the web page stays a thin
skin: it renders these tables and posts back the ids.
"""
import copy
import os

import gamedir

DEFAULT_PAK_NAME = 'pakchunk9999-Mods_MaxSuspect_P.pak'
DEFAULT_MODS_SUBFOLDER = 'ZZZ-MaxSuspectGen'

# ---------------------------------------------------------------- spawn counts
#
# Two ways to ask for bodies:
#   multiplier - scale whatever each map already declares, so Hospital stays
#                busier than Gas Station
#   flat       - one min/max on every map
#
# The flat ceilings are not arbitrary.  Vanilla maps run 4-21 suspects; the
# highest-count mod that currently works ships a flat 25-60 on every map with
# spawn groups switched off.  Four-figure numbers do not give you four-figure
# firefights - they make maps spawn nobody at all.

# MAX is a single number, not a range: min == max, so the game cannot roll
# low and you get the same fight every time.  It is deliberately far above any
# map's spawn-point count - the game clamps to what a map actually holds, so
# "100" means "everything this map has".
#
# How high is safe is the one thing here that cannot be checked without
# playing.  Known data points: the current highest-count difficulty mod ships
# a flat 25-60 and works; a build at 1000 with spawn groups left on produced
# empty maps.  100 sits well clear of any map's capacity without going
# anywhere near the number that failed.  If a map spawns nobody, this is the
# first dial to turn down.
MAX_VALUE = 100
MAX_CIVILIAN_VALUE = 30

FLAT_SUSPECTS = {'min': 25, 'max': 60}
FLAT_CIVILIANS = {'min': 8, 'max': 20}
SANE_CEILING = 200

SUSPECT_MULTS = [0.5, 1.0, 1.5, 2.0, 3.0]
CIVILIAN_MULTS = [0.5, 1.0, 1.5, 2.0]
ROAMING_MULTS = [0.0, 0.5, 1.0, 2.0, 3.0]
TRAP_MULTS = [0.5, 1.0, 2.0]
HP_MULTS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]

COUNT_KINDS = [
    {'id': 'mult', 'label': 'Multiplier', 'note': 'scale each map’s own numbers'},
    {'id': 'flat', 'label': 'Flat range', 'note': 'the same min/max on every map'},
    {'id': 'max', 'label': 'MAX',
     'note': 'one high number, min = max, clamped to what each map can hold'},
]
CIVILIAN_KINDS = COUNT_KINDS + [
    {'id': 'none', 'label': 'None', 'note': 'no civilians anywhere'},
]

# -------------------------------------------------------------- accuracy tiers
#
# SuspectAccuracy is a cone in degrees: 0 is a perfect shot, 5+ cannot hit
# anything past 10m.  The supporting keys decide how that cone grows with
# range and movement, and how long a suspect tracks you before firing --
# tuning accuracy without them just makes enemies miss from a different place.

_WEAPON_CONES = ['Rifle', 'SMG', 'LMG', 'Pistol', 'Shotgun', 'LessLethal', 'Default']


def _weapon_cone(mult):
    return {'Suspect%sAccuracyOffsetMultiplier' % w: mult for w in _WEAPON_CONES}


ACCURACY_TIERS = {
    'blind': {
        'label': 'Blind', 'note': 'they can barely hit you',
        'keys': {
            'SuspectAccuracy': 9.0,
            'ShrinkAccuracyConeAtRangeScale': 0.3,
            'SuspectAccuracyLostPerTenMetersToTarget': 0.6,
            'SuspectAccuracyLostPerMeterSecond': 0.12,
            'SuspectSightStimulusReactionTime': 1.2,
            'SuspectRequiredTimeSpentOnTarget': 0.8,
            'SuspectTimeWithWeaponUpBeforeFiring': 0.9,
            **_weapon_cone(1.6),
        },
    },
    'worse': {
        'label': 'Worse', 'note': 'sloppier than vanilla',
        'keys': {
            'SuspectAccuracy': 5.0,
            'ShrinkAccuracyConeAtRangeScale': 0.7,
            'SuspectAccuracyLostPerTenMetersToTarget': 0.2,
            'SuspectAccuracyLostPerMeterSecond': 0.07,
            'SuspectSightStimulusReactionTime': 0.5,
            'SuspectRequiredTimeSpentOnTarget': 0.3,
            'SuspectTimeWithWeaponUpBeforeFiring': 0.5,
            **_weapon_cone(1.2),
        },
    },
    'vanilla': {'label': 'Vanilla', 'note': 'untouched', 'keys': {}},
    'accurate': {
        'label': 'Accurate', 'note': 'they shoot straight',
        'keys': {
            'SuspectAccuracy': 1.0,
            'ShrinkAccuracyConeAtRangeScale': 2.5,
            'SuspectAccuracyLostPerTenMetersToTarget': 0.0,
            'SuspectAccuracyLostPerMeterSecond': 0.01,
            'SuspectSightStimulusReactionTime': 0.12,
            'SuspectRequiredTimeSpentOnTarget': 0.03,
            'SuspectTimeWithWeaponUpBeforeFiring': 0.05,
            'SuspectAlertReactionTimeMultiplier': 0.2,
            **_weapon_cone(0.5),
        },
    },
    'aimbot': {
        'label': 'Aimbot', 'note': 'instant, perfect, merciless',
        'keys': {
            'SuspectAccuracy': 0.0,
            'ShrinkAccuracyConeAtRangeScale': 5.0,
            'SuspectAccuracyLostPerTenMetersToTarget': 0.0,
            'SuspectAccuracyLostPerMeterSecond': 0.0,
            'SuspectSightStimulusReactionTime': 0.0,
            'SuspectSoundStimulusReactionTime': 0.0,
            'SuspectDamageStimulusReactionTime': 0.0,
            'SuspectSightReactionTimeIncreasePerTwentyMeters': 0.0,
            'SuspectAlertReactionTimeMultiplier': 0.0,
            'SuspectSuspiciousReactionTimeMultiplier': 0.0,
            'SuspectRequiredTimeSpentOnTarget': 0.0,
            'SuspectTimeWithWeaponUpBeforeFiring': 0.0,
            'SuspectEngagementTimeResetOnLOSLossTime': 0.0,
            'StressUntilWeaponRaise': 0.0,
            'SuspectStartingStress': 0.0,
            **_weapon_cone(0.0),
        },
    },
}
ACCURACY_ORDER = ['blind', 'worse', 'vanilla', 'accurate', 'aimbot']

# --------------------------------------------------------------------- health

HP_MODES = [
    {'id': 'vanilla', 'label': 'Per map (vanilla)',
     'note': 'keeps each map’s own tuning, scaled'},
    {'id': 'consistent', 'label': 'Consistent',
     'note': 'one number on every map'},
]

# ------------------------------------------------------------------- surrender
#
# Every AI carries a hidden morale value from 0.0 to 1.0, rolled at spawn
# between its Min and Max and drained by shouting, flashbangs, tasers, seeing
# a friend go down, doors coming in.  Low morale is what makes them give up.
# So "gives up easily" means starting them closer to broken, and the other end
# means starting them at the ceiling.
#
# Only faction-specific keys belong here.  MoraleDamageRate and the yell
# damage keys apply to suspects and civilians alike, so putting them in one
# side's tier would quietly move the other; they live in Advanced instead.
#
# MaxMorale is what map sections call SuspectMaxMorale.  It does not exist in
# [Global], so it is applied only where it already appears.
SURRENDER_ALIAS = {'MaxMorale'}

SUSPECT_SURRENDER = {
    'easy': {
        'label': 'Gives up easily', 'note': 'starts shaken and folds under pressure',
        'keys': {
            'SuspectMinMorale': 0.25,
            'SuspectMaxMorale': 0.5,
            'MaxMorale': 0.5,
            'SuspectNonCompliantMorale.Gain': 0.02,
            'ChanceToSurrenderWithItem': 0.6,
            'SuspectFakeSurrenderChance': 0.2,
            'ChanceToFakeSurrenderWhenOrderedToTurnAround': 0.0,
            'SurrenderExitMinTime': 60.0,
            'HesitationChanceArmed': 0.5,
            'HesitationTimeArmed': 7.0,
            'PlayDeadChance': 0.05,
            'SuicideChance': 0.02,
        },
    },
    'vanilla': {'label': 'Vanilla', 'note': 'untouched', 'keys': {}},
    'hard': {
        'label': 'Fights to the end',
        'note': 'near unbreakable, and fakes it when they do go down',
        'keys': {
            'SuspectMinMorale': 0.95,
            'SuspectMaxMorale': 1.0,
            'MaxMorale': 1.0,
            'SuspectNonCompliantMorale.Gain': 0.3,
            'ChanceToSurrenderWithItem': 0.0,
            'SuspectFakeSurrenderChance': 1.0,
            'ChanceToFakeSurrenderWhenOrderedToTurnAround': 0.5,
            'SurrenderExitMinTime': 5.0,
            'HesitationChanceArmed': 0.0,
            'HesitationTimeArmed': 0.5,
            'PlayDeadChance': 0.4,
            'SuicideChance': 0.25,
        },
    },
}

CIVILIAN_SURRENDER = {
    'easy': {
        'label': 'Complies quickly', 'note': 'drops and stays down when told',
        'keys': {
            'CivilianMinMorale': 0.15,
            'CivilianMaxMorale': 0.4,
            'CivilianNonCompliantMorale.Gain': 0.005,
        },
    },
    'vanilla': {'label': 'Vanilla', 'note': 'untouched', 'keys': {}},
    'hard': {
        'label': 'Panics and runs', 'note': 'ignores orders and keeps moving',
        'keys': {
            'CivilianMinMorale': 0.9,
            'CivilianMaxMorale': 1.0,
            'CivilianNonCompliantMorale.Gain': 0.1,
        },
    },
}
SURRENDER_ORDER = ['easy', 'vanilla', 'hard']


# ------------------------------------------------------------- extra AI tiers
#
# Four more bundles, all of them settings the game ships and the community
# documentation describes.  Each is a group of keys that only makes sense
# moved together: raising sight range without hearing range, or stun duration
# without stun health, produces incoherent AI.

DOOR_TIERS = {
    'open': {
        'label': 'Wide open', 'note': 'nothing locked, plenty already ajar',
        'keys': {'MaxLockedDoorsPercentage': 0.0, 'MaxOpenDoorsPercentage': 0.6,
                 'MaxKeycards': 4},
    },
    'vanilla': {'label': 'Vanilla', 'note': '20% locked, 20% open', 'keys': {}},
    'locked': {
        'label': 'Locked down', 'note': 'most doors locked, nothing left open',
        'keys': {'MaxLockedDoorsPercentage': 0.75, 'MaxOpenDoorsPercentage': 0.0},
    },
}
DOOR_ORDER = ['open', 'vanilla', 'locked']

# Stun health is a pool that less-lethals deplete; the AI drops when it hits
# zero. So "strong" lowers the pool and raises every source's damage.
LESS_LETHAL_TIERS = {
    'weak': {
        'label': 'Weak', 'note': 'less-lethals barely register',
        'keys': {'StunHealth': 200, 'AIStunDuration': 2.0, 'BeanbagStunDuration': 0.75,
                 'AINineBangerStunDuration': 2, 'GrenadeStunDamage': 50,
                 'TaserStunDamage': 60, 'PepperballStunDamage': 9,
                 'RubberballStunDamage': 50, 'BeanbagShotgunStunDamage': 50,
                 'GasStunDamage': 8, 'NineBangerAccuracyPenalty': 0.02,
                 'AccuracyPenaltyRecovery': 0.05, 'PepperSprayAccuracyPenalty': 5.0},
    },
    'vanilla': {'label': 'Vanilla', 'note': 'untouched', 'keys': {}},
    'strong': {
        'label': 'Strong', 'note': 'flashbangs and tasers actually win fights',
        'keys': {'StunHealth': 60, 'AIStunDuration': 8.0, 'BeanbagStunDuration': 4.0,
                 'AINineBangerStunDuration': 9, 'GrenadeStunDamage': 150,
                 'TaserStunDamage': 150, 'PepperballStunDamage': 40,
                 'RubberballStunDamage': 150, 'BeanbagShotgunStunDamage': 150,
                 'GasStunDamage': 30, 'NineBangerAccuracyPenalty': 0.15,
                 'AccuracyPenaltyRecovery': 0.01, 'PepperSprayAccuracyPenalty': 20.0},
    },
}
LESS_LETHAL_ORDER = ['weak', 'vanilla', 'strong']

# Distances are centimetres. The two PerceptionHalfAngle keys are documented
# but absent from the stock file, so they are appended rather than rewritten.
AWARENESS_TIERS = {
    'oblivious': {
        'label': 'Oblivious', 'note': 'short sight, poor hearing, short memory',
        'keys': {'UnalertedSightRange': 1500, 'SuspiciousSightRange': 2000,
                 'AlertedSightRange': 3500, 'GunShotHearingRange': 900.0,
                 'DoorKickHearingRange': 800.0, 'FlashlightPerceptionRange': 600.0,
                 'GrenadePerceptionRange': 700, 'GunShotForgetTime': 8.0,
                 'FlashlightForgetTime': 0.3, 'SightDetectionAccuracy': 0.0,
                 'SuspectTrackLastKnownPositionTime': 15.0,
                 'UnalertedPerceptionHalfAngle': 55, 'AlertedPerceptionHalfAngle': 90},
    },
    'vanilla': {'label': 'Vanilla', 'note': 'untouched', 'keys': {}},
    'sharp': {
        'label': 'Eagle-eyed', 'note': 'sees far, hears everything, forgets nothing',
        'keys': {'UnalertedSightRange': 8000, 'SuspiciousSightRange': 9000,
                 'AlertedSightRange': 15000, 'GunShotHearingRange': 6000.0,
                 'DoorKickHearingRange': 5000.0, 'FlashlightPerceptionRange': 4000.0,
                 'GrenadePerceptionRange': 4000, 'GunShotForgetTime': 90.0,
                 'FlashlightForgetTime': 3.0, 'SightDetectionAccuracy': 1.0,
                 'SuspectTrackLastKnownPositionTime': 180.0,
                 'UnalertedPerceptionHalfAngle': 120, 'AlertedPerceptionHalfAngle': 170},
    },
}
AWARENESS_ORDER = ['oblivious', 'vanilla', 'sharp']

# SuspectAccuracyLostPerMeterSecond is how many degrees of aim cone a suspect
# gives up per m/s of its OWN movement - the game's own comment puts the average
# speed while shooting at ~2.3 m/s.  Vanilla sets it around 0.035-0.045, which
# at that speed widens a 2.5 degree cone by about 3 percent: near enough to
# nothing, which is why sprinting suspects still hit you.  One stock map section
# already uses 0.3, so the higher numbers here are in territory the game itself
# treats as valid.

MOVING_ACCURACY_TIERS = {
    'heavy': {
        'label': "Can't run and shoot",
        'note': 'roughly doubles the cone at a walk, useless at a sprint',
        'keys': {'SuspectAccuracyLostPerMeterSecond': 1.2},
    },
    'nerf': {
        'label': 'Worse on the move',
        'note': 'noticeably wilder while moving, still dangerous',
        'keys': {'SuspectAccuracyLostPerMeterSecond': 0.4},
    },
    'vanilla': {'label': 'Vanilla', 'note': 'a ~3% penalty, i.e. barely any',
                'keys': {}},
    'full': {
        'label': 'No penalty',
        'note': 'shoots as well running as standing still',
        'keys': {'SuspectAccuracyLostPerMeterSecond': 0.0},
    },
}
MOVING_ACCURACY_ORDER = ['heavy', 'nerf', 'vanilla', 'full']

# SwatHealth is your AI teammates only - the player's own durability lives in
# the armour assets, not in Difficulty.ini, so it is out of reach here.  Health
# and marksmanship are split because wanting tanky-but-useless teammates (or the
# reverse) is a common ask.

SWAT_HP_TIERS = {
    'weak': {
        'label': 'Fragile', 'note': 'teammates drop fast (120 hp)',
        'keys': {'SwatHealth': 120.0},
    },
    'vanilla': {'label': 'Vanilla', 'note': 'untouched (200 hp)', 'keys': {}},
    'strong': {
        'label': 'Tanky', 'note': 'teammates soak hits (400 hp)',
        'keys': {'SwatHealth': 400.0},
    },
}
SWAT_HP_ORDER = ['weak', 'vanilla', 'strong']

SWAT_TIERS = {
    'weak': {
        'label': 'Liability', 'note': 'slow to react and a poor shot',
        'keys': {'SwatAccuracy': 6.0,
                 'SWATRequiredTimeSpentOnTarget': 0.4,
                 'SwatTimeWithWeaponUpBeforeFiring': 0.6,
                 'SwatSightStimulusReactionTime': 0.6,
                 'SwatTrackLastKnownPositionTime': 2.0},
    },
    'vanilla': {'label': 'Vanilla', 'note': 'untouched', 'keys': {}},
    'strong': {
        'label': 'Elite', 'note': 'instant reactions, deadly accurate',
        'keys': {'SwatAccuracy': 1.0,
                 'SWATRequiredTimeSpentOnTarget': 0.02,
                 'SwatTimeWithWeaponUpBeforeFiring': 0.03,
                 'SwatSightStimulusReactionTime': 0.05,
                 'SwatTrackLastKnownPositionTime': 20.0},
    },
}
SWAT_ORDER = ['weak', 'vanilla', 'strong']

# ---------------------------------------------------------------------- traps
#
# Only ten maps declare traps of their own; the rest inherit [Global].
# ToxicGas and TowerAlarm appear on one map each and look map-specific, so
# "all types" means the three the game itself lists globally.

TRAP_TYPES_ALL = 'Explosive, Flashbang, Alarm'
TRAP_BASE = 6

TRAP_MODES = [
    {'id': 'removed', 'label': 'Removed', 'note': 'no traps on any map'},
    {'id': 'vanilla', 'label': 'Vanilla', 'note': 'only the ten maps that ship them'},
    {'id': 'all', 'label': 'All maps, all types',
     'note': 'every map gets explosive, flashbang and alarm traps'},
]

# -------------------------------------------------------------------- presets


def _s(kind='mult', factor=1.0):
    return {'kind': kind, 'factor': factor, 'value': MAX_VALUE,
            'min': FLAT_SUSPECTS['min'], 'max': FLAT_SUSPECTS['max']}


def _c(kind='mult', factor=1.0):
    return {'kind': kind, 'factor': factor, 'value': MAX_CIVILIAN_VALUE,
            'min': FLAT_CIVILIANS['min'], 'max': FLAT_CIVILIANS['max']}


def _p(susp, civ, acc, roam, hp_mode, hp, trap_mode, trap=1.0,
       give_up='vanilla', civ_give_up='vanilla', doors='vanilla',
       lesslethal='vanilla', awareness='vanilla', swat='vanilla',
       swat_hp='vanilla', moving='vanilla'):
    return {'suspects': susp, 'civilians': civ, 'accuracy': acc,
            'roaming': {'factor': roam},
            'health': {'mode': hp_mode, 'factor': hp},
            'traps': {'mode': trap_mode, 'factor': trap},
            'surrender': {'suspects': give_up, 'civilians': civ_give_up},
            'doors': doors, 'lesslethal': lesslethal,
            'awareness': awareness, 'swat': swat, 'swat_hp': swat_hp,
            'moving': moving}


PRESETS = [
    {'id': 'vanilla', 'name': 'Vanilla',
     'blurb': 'Nothing changed. Use it to confirm the mod installs and loads.',
     'settings': _p(_s(), _c(), 'vanilla', 1.0, 'vanilla', 1.0, 'vanilla')},
    {'id': 'max-suspect', 'name': 'MAX SUSPECT',
     'blurb': 'Vanilla in every respect but one: every map packed to its spawn '
              'limit. The honest version of the classic.',
     'settings': _p(_s('max'), _c(), 'vanilla', 1.0, 'vanilla', 1.0, 'vanilla')},
    {'id': 'swarm', 'name': 'Swarm',
     'blurb': 'Twice the bodies, vanilla aim, slightly softer. Busy but fair.',
     'settings': _p(_s('mult', 2.0), _c(), 'vanilla', 2.0, 'vanilla', 0.75, 'vanilla')},
    {'id': 'meat-grinder', 'name': 'Meat Grinder',
     'blurb': 'Max suspects, perfect aim, roaming everywhere, traps on every '
              'map. You are not going to win this one.',
     'settings': _p(_s('max'), _c('none'), 'aimbot', 3.0, 'consistent', 1.0,
                    'all', 2.0, give_up='hard', doors='locked',
                    awareness='sharp', lesslethal='weak', moving='full')},
    {'id': 'hostage-crisis', 'name': 'Hostage Crisis',
     'blurb': 'Packed with civilians and half again as many suspects. '
              'Every trigger pull is a decision.',
     'settings': _p(_s('mult', 1.5), _c('flat'), 'vanilla', 1.0,
                    'vanilla', 1.0, 'vanilla', civ_give_up='hard')},
    {'id': 'minefield', 'name': 'Minefield',
     'blurb': 'Vanilla firefights, but every door might be wired. Slow down '
              'and check your corners.',
     'settings': _p(_s(), _c(), 'vanilla', 1.0, 'vanilla', 1.0, 'all', 2.0,
                    doors='locked')},
    {'id': 'tactical-realism', 'name': 'Tactical Realism',
     'blurb': 'Vanilla numbers, sharp suspects, low health both ways. '
              'Fights end in one or two rounds.',
     'settings': _p(_s(), _c(), 'accurate', 1.0, 'consistent', 0.5, 'vanilla',
                    lesslethal='strong', swat='strong', swat_hp='strong',
                    moving='nerf')},
    {'id': 'bullet-sponge', 'name': 'Bullet Sponge',
     'blurb': 'Vanilla counts, double health, good aim. Shot placement matters.',
     'settings': _p(_s(), _c(), 'accurate', 1.0, 'consistent', 2.0, 'vanilla')},
    {'id': 'glass-cannon', 'name': 'Glass Cannon',
     'blurb': 'Aimbot suspects made of paper, roaming hard. Speed and angles '
              'or nothing.',
     'settings': _p(_s('mult', 1.5), _c('none'), 'aimbot', 3.0,
                    'consistent', 0.5, 'vanilla', give_up='hard',
                    awareness='sharp', moving='full')},
    {'id': 'training-day', 'name': 'Training Day',
     'blurb': 'Half the suspects, terrible aim, soft targets, no traps. '
              'For learning maps.',
     'settings': _p(_s('mult', 0.5), _c(), 'blind', 0.5, 'vanilla', 0.5, 'removed',
                    give_up='easy', civ_give_up='easy', doors='open',
                    awareness='oblivious', lesslethal='strong', swat='strong',
                    swat_hp='strong', moving='heavy')},
    {'id': 'lockdown', 'name': 'Lockdown',
     'blurb': 'Vanilla counts, but the building is sealed and everyone inside is '
              'paying attention. A breaching and stealth problem.',
     'settings': _p(_s(), _c(), 'vanilla', 1.5, 'vanilla', 1.0, 'all', 1.0,
                    doors='locked', awareness='sharp')},
    {'id': 'non-lethal', 'name': 'Non-Lethal Run',
     'blurb': 'Flashbangs, tasers and beanbags actually work, and suspects break '
              'when pressed. Built for arresting everyone.',
     'settings': _p(_s('mult', 1.5), _c(), 'vanilla', 1.0, 'vanilla', 1.0, 'vanilla',
                    give_up='easy', civ_give_up='easy', lesslethal='strong')},
]

DEFAULT_SETTINGS = {
    'preset': 'max-suspect',
    'suspects': _s('max'),
    'civilians': _c(),
    'accuracy': 'vanilla',
    'roaming': {'factor': 1.0},
    'health': {'mode': 'vanilla', 'factor': 1.0},
    'traps': {'mode': 'vanilla', 'factor': 1.0},
    'surrender': {'suspects': 'vanilla', 'civilians': 'vanilla'},
    'doors': 'vanilla',
    'lesslethal': 'vanilla',
    'awareness': 'vanilla',
    'swat': 'vanilla',
    'swat_hp': 'vanilla',
    'moving': 'vanilla',
    'advanced': {
        'game_dir': '',
        'difficulties': ['HardDifficulty', 'StandardDifficulty', 'CasualDifficulty'],
        'install_to': 'paks',
        'pak_name': DEFAULT_PAK_NAME,
        'apply_global_to_map_sections': True,
        'spawn_groups': 'flat',
        'trap_types': TRAP_TYPES_ALL,
        'trap_base': TRAP_BASE,
        'global': {},
        'map': {},
    },
}

# Keys the roaming multiplier scales.  MaxRoamingCivilians is deliberately not
# here: "roaming suspects" should not quietly move civilians around too.
ROAMING_KEYS = ['MinRoamingSuspects', 'MaxRoamingSuspects', 'HRMaxRoamers']

SUSPECT_DEFAULTS = dict(FLAT_SUSPECTS, value=MAX_VALUE)
CIVILIAN_DEFAULTS = dict(FLAT_CIVILIANS, value=MAX_CIVILIAN_VALUE)


# ------------------------------------------------------------------- assembly

def _count_block(spec, defaults):
    kind = spec.get('kind', 'mult')
    if kind == 'none':
        return {'enable': True, 'mode': 'fixed', 'total_min': 0, 'total_max': 0,
                'group_min': 0, 'group_max': 0}
    if kind == 'max':
        v = max(0, int(spec.get('value', defaults['value'])))
        return {'enable': True, 'mode': 'fixed', 'total_min': v, 'total_max': v,
                'group_min': max(1, v // 4), 'group_max': max(1, v // 4)}
    if kind == 'flat':
        lo = max(0, int(spec.get('min', defaults['min'])))
        hi = max(0, int(spec.get('max', defaults['max'])))
        if hi < lo:
            lo, hi = hi, lo
        return {'enable': True, 'mode': 'fixed', 'total_min': lo, 'total_max': hi,
                'group_min': max(1, lo // 4), 'group_max': max(1, hi // 4)}
    factor = float(spec.get('factor', 1.0))
    if factor == 1.0:
        return {'enable': True, 'mode': 'off'}
    return {'enable': True, 'mode': 'multiply', 'factor': factor}


def build_conf(settings):
    """Map UI settings onto the config dict `generate.build` consumes."""
    s = copy.deepcopy(DEFAULT_SETTINGS)
    for key in ('preset', 'accuracy', 'doors', 'lesslethal', 'awareness',
                'swat', 'swat_hp', 'moving'):
        if key in settings:
            s[key] = settings[key]
    for key in ('suspects', 'civilians', 'roaming', 'health', 'traps',
                'surrender'):
        if isinstance(settings.get(key), dict):
            s[key].update(settings[key])
    adv = s['advanced']
    adv.update(settings.get('advanced') or {})

    game_dir = gamedir.detect(adv.get('game_dir'))
    if adv.get('install_to') == 'mods':
        deploy_to = os.path.join(gamedir.mods_dir(game_dir), DEFAULT_MODS_SUBFOLDER)
    else:
        deploy_to = gamedir.paks_dir(game_dir)

    label = next((p['name'] for p in PRESETS if p['id'] == s.get('preset')), 'Custom')

    conf = {
        'mod': {
            'name': 'MaxSuspectGen',
            'pak_name': adv.get('pak_name') or DEFAULT_PAK_NAME,
            'deploy_to': deploy_to,
            'marker': 'MaxSuspectGen: %s' % label,
        },
        'source': {
            'game_dir': game_dir,
            'difficulties': list(adv.get('difficulties') or
                                 DEFAULT_SETTINGS['advanced']['difficulties']),
        },
        'options': {
            'apply_global_to_map_sections': bool(
                adv.get('apply_global_to_map_sections', True)),
            'spawn_groups': adv.get('spawn_groups', 'flat'),
        },
        'suspects': _count_block(s['suspects'], SUSPECT_DEFAULTS),
        'civilians': _count_block(s['civilians'], CIVILIAN_DEFAULTS),
        'traps': {
            'mode': s['traps'].get('mode', 'vanilla'),
            'factor': float(s['traps'].get('factor', 1.0)),
            'base': int(adv.get('trap_base', TRAP_BASE)),
            'types': adv.get('trap_types', TRAP_TYPES_ALL),
        },
        'roaming': {},
        'global': {},
        'global_if_present': {},
        'global_scale': {},
        'global_scale_flat': {},
        'global_by_difficulty': {},
        'map': {k: dict(v) for k, v in (adv.get('map') or {}).items()},
    }

    conf['global'].update(ACCURACY_TIERS.get(s['accuracy'], {}).get('keys', {}))

    for table, pick in ((SUSPECT_SURRENDER, s['surrender'].get('suspects', 'vanilla')),
                        (CIVILIAN_SURRENDER, s['surrender'].get('civilians', 'vanilla')),
                        (DOOR_TIERS, s['doors']),
                        (LESS_LETHAL_TIERS, s['lesslethal']),
                        (AWARENESS_TIERS, s['awareness']),
                        (SWAT_TIERS, s['swat']),
                        (SWAT_HP_TIERS, s['swat_hp']),
                        (MOVING_ACCURACY_TIERS, s['moving'])):
        for k, v in table.get(pick, {}).get('keys', {}).items():
            target = conf['global_if_present'] if k in SURRENDER_ALIAS else conf['global']
            target[k] = v

    roam = float(s['roaming'].get('factor', 1.0))
    if roam != 1.0:
        for k in ROAMING_KEYS:
            conf['global_scale'][k] = roam

    hp = float(s['health'].get('factor', 1.0))
    if s['health'].get('mode') == 'consistent':
        conf['global_scale_flat']['SuspectHealth'] = hp
    elif hp != 1.0:
        conf['global_scale']['SuspectHealth'] = hp

    # Advanced free-form keys win over everything the simple controls set.
    conf['global'].update(adv.get('global') or {})
    return conf


def catalogue():
    """Everything the page needs in order to render itself."""
    return {
        'presets': PRESETS,
        'count_kinds': COUNT_KINDS,
        'civilian_kinds': CIVILIAN_KINDS,
        'suspect_mults': SUSPECT_MULTS,
        'civilian_mults': CIVILIAN_MULTS,
        'roaming_mults': ROAMING_MULTS,
        'trap_mults': TRAP_MULTS,
        'hp_mults': HP_MULTS,
        'hp_modes': HP_MODES,
        'trap_modes': TRAP_MODES,
        'suspect_surrender': [dict(id=t, label=SUSPECT_SURRENDER[t]['label'],
                                   note=SUSPECT_SURRENDER[t]['note'])
                              for t in SURRENDER_ORDER],
        'civilian_surrender': [dict(id=t, label=CIVILIAN_SURRENDER[t]['label'],
                                    note=CIVILIAN_SURRENDER[t]['note'])
                               for t in SURRENDER_ORDER],
        'door_tiers': [dict(id=t, label=DOOR_TIERS[t]['label'],
                            note=DOOR_TIERS[t]['note']) for t in DOOR_ORDER],
        'lesslethal_tiers': [dict(id=t, label=LESS_LETHAL_TIERS[t]['label'],
                                  note=LESS_LETHAL_TIERS[t]['note'])
                             for t in LESS_LETHAL_ORDER],
        'awareness_tiers': [dict(id=t, label=AWARENESS_TIERS[t]['label'],
                                 note=AWARENESS_TIERS[t]['note'])
                            for t in AWARENESS_ORDER],
        'swat_tiers': [dict(id=t, label=SWAT_TIERS[t]['label'],
                            note=SWAT_TIERS[t]['note']) for t in SWAT_ORDER],
        'swat_hp_tiers': [dict(id=t, label=SWAT_HP_TIERS[t]['label'],
                               note=SWAT_HP_TIERS[t]['note'])
                          for t in SWAT_HP_ORDER],
        'moving_accuracy_tiers': [dict(id=t, label=MOVING_ACCURACY_TIERS[t]['label'],
                                       note=MOVING_ACCURACY_TIERS[t]['note'])
                                  for t in MOVING_ACCURACY_ORDER],
        'accuracy_tiers': [dict(id=t, label=ACCURACY_TIERS[t]['label'],
                                note=ACCURACY_TIERS[t]['note'])
                           for t in ACCURACY_ORDER],
        'defaults': DEFAULT_SETTINGS,
        'max_value': MAX_VALUE,
        'max_civilian_value': MAX_CIVILIAN_VALUE,
        'flat_suspects': FLAT_SUSPECTS,
        'flat_civilians': FLAT_CIVILIANS,
        'sane_ceiling': SANE_CEILING,
    }
