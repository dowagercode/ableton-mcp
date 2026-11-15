"""Tests for the Main / return track indices, the mixer commands and delete_device.

* track_index -1 means the Main track and -2, -3 ... the return tracks, for the
  commands that take a track; 0 and up are the ordinary tracks as before,
* get_track_mixer / set_track_mixer read and set a fader in dB and a pan,
* delete_device refuses when the device at the index has a different name.

Live's objects are faked; no Ableton, no network.
"""

import math

import pytest

from test_remote_script_bridge import _load_script_module, make_instance


@pytest.fixture(scope="module")
def script_module():
    return _load_script_module()


class FakeParam(object):
    def __init__(self, value, lo, hi, text):
        self.value, self.min, self.max, self._text = value, lo, hi, text

    def str_for_value(self, v):
        return self._text(v)


def fader_text(v):
    """A made-up fader curve, monotonic like Live's: 0.85 is 0 dB, 1.0 is +6 dB, 0 is -inf."""
    if v <= 0:
        return "-inf dB"
    db = 40 * math.log10(v / 0.85) if v < 0.85 else 6 * (v - 0.85) / 0.15
    return "%.1f dB" % db


class FakeMixer(object):
    def __init__(self):
        self.volume = FakeParam(0.85, 0.0, 1.0, fader_text)
        self.panning = FakeParam(0.0, -1.0, 1.0, lambda v: "%.0f" % (v * 50))


class FakeDevice(object):
    def __init__(self, name):
        self.name = name


class FakeTrack(object):
    def __init__(self, name, devices=()):
        self.name = name
        self.mixer_device = FakeMixer()
        self.devices = [FakeDevice(d) for d in devices]

    def delete_device(self, i):
        del self.devices[i]


class FakeSong(object):
    def __init__(self):
        self.tracks = [FakeTrack("Drums", ["EQ Eight", "Compressor"]), FakeTrack("Bass")]
        self.return_tracks = [FakeTrack("A-Reverb"), FakeTrack("B-Delay")]
        self.master_track = FakeTrack("Main", ["Limiter"])


@pytest.fixture
def inst(script_module):
    i = make_instance(script_module)
    i._song = FakeSong()
    return i


# ------------------------------------------------------------ track indices

def test_track_indices_reach_main_and_returns(inst):
    assert inst._track_at(0).name == "Drums"
    assert inst._track_at(1).name == "Bass"
    assert inst._track_at(-1).name == "Main"
    assert inst._track_at(-2).name == "A-Reverb"
    assert inst._track_at(-3).name == "B-Delay"


def test_track_indices_out_of_range_still_raise(inst):
    with pytest.raises(IndexError):
        inst._track_at(2)
    with pytest.raises(IndexError):
        inst._track_at(-4)


def test_set_track_name_works_on_a_return(inst):
    inst._set_track_name(-2, "Plate")
    assert inst._song.return_tracks[0].name == "Plate"


# ------------------------------------------------------------------- mixer

def test_get_track_mixer_reports_db_and_pan(inst):
    m = inst._mixer_state(inst._track_at(-1))
    assert m["name"] == "Main"
    assert m["volume_db"] == 0.0
    assert m["volume_text"] == "0.0 dB"
    assert m["pan"] == 0.0


@pytest.mark.parametrize("db", [-6.0, -3.5, -20.0, 3.0])
def test_set_track_mixer_lands_on_the_level_asked_for(inst, db):
    out = inst._set_track_mixer(0, volume_db=db)
    assert out["after"]["volume_db"] == pytest.approx(db, abs=0.05)
    assert out["before"]["volume_db"] == 0.0


def test_set_track_mixer_holds_the_fader_at_its_top(inst):
    out = inst._set_track_mixer(1, volume_db=20.0)
    assert inst._song.tracks[1].mixer_device.volume.value == 1.0
    assert out["after"]["volume_db"] == 6.0


def test_set_track_mixer_pan_only_leaves_the_fader(inst):
    inst._set_track_mixer(-3, pan=-0.25)
    t = inst._song.return_tracks[1]
    assert t.mixer_device.panning.value == -0.25
    assert t.mixer_device.volume.value == 0.85


def test_set_track_mixer_clamps_pan(inst):
    inst._set_track_mixer(0, pan=3.0)
    assert inst._song.tracks[0].mixer_device.panning.value == 1.0


# ----------------------------------------------------------- delete_device

def test_delete_device_removes_the_named_device(inst):
    out = inst._delete_device(0, 1, "Compressor")
    assert out == {"deleted": "Compressor", "devices": ["EQ Eight"]}


def test_delete_device_refuses_a_name_that_does_not_match(inst):
    with pytest.raises(ValueError):
        inst._delete_device(0, 0, "Compressor")
    assert [d.name for d in inst._song.tracks[0].devices] == ["EQ Eight", "Compressor"]


def test_delete_device_on_main(inst):
    inst._delete_device(-1, 0, "Limiter")
    assert inst._song.master_track.devices == []


def test_delete_device_index_out_of_range(inst):
    with pytest.raises(IndexError):
        inst._delete_device(1, 0, "Anything")


# ------------------------------------------------------------ capabilities

def test_new_commands_are_advertised(script_module):
    for name in ("main_and_return_tracks", "get_track_mixer", "set_track_mixer", "delete_device"):
        assert name in script_module.SCRIPT_CAPABILITIES
