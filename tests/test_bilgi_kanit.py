"""Deterministic direction, high impact and rune-parent regressions."""
import pytest
from core import bilgi_kanit as k, varlik_grafigi as vg

def relation(s,r,o,e): return {"ozne":s,"iliski":r,"nesne":o,"kanit":e}

@pytest.mark.parametrize("student,teacher", [("Ada","Boris"),("Nila","Orion")])
def test_teacher_roles(student,teacher):
 e=f"{teacher} taught {student} how to wield a spear."
 assert k.semantik_sonuc(relation(student,"ogretmeni",teacher,e),{})[0]=="verified"
 assert k.semantik_sonuc(relation(teacher,"ogretmeni",student,e),{})==( "wrong","direction_reversed")

@pytest.mark.parametrize("e",["Ada stabbed Boris.","Ada defeated Boris.","Ada tried to kill Boris.","Ada never killed Boris.","Ada wounded Boris."])
def test_attack_is_not_kill(e):
 assert k.semantik_sonuc(relation("Ada","oldurdu","Boris",e),{})[0]=="wrong"

def test_explicit_kill():
 assert k.semantik_sonuc(relation("Ada","oldurdu","Boris","Ada killed Boris."),{})[0]=="verified"

def test_ordinary_name_not_true_name():
 assert k.semantik_sonuc(relation("Prince","gercek_adi","Nether","Prince was named Nether."),{})==( "wrong","ordinary_name_is_not_true_name")
 assert k.semantik_sonuc(relation("Ada","gercek_adi","Bright Star","Ada's True Name was Bright Star."),{})[0]=="verified"

def test_state_requires_actual_subject_and_life():
 x={"varlik":"Ada","anahtar":"Yaşam","makine_anahtari":"life_status","deger":"dead","durum_bilgisi":"confirmed","kanit":"Ada stabbed Boris."}
 assert not k.state_kaniti(x,x["kanit"],{},[])[0]
 x["kanit"]="Ada watched Boris die."
 assert not k.state_kaniti(x,x["kanit"],{},[])[0]
 x["kanit"]="Ada was dead."
 assert k.state_kaniti(x,x["kanit"],{},[])[0]

def test_shadow_block_resumes_only_shadow_fields():
 s="Shadow: Granite Guard.\nShadow Attributes: [Battle Master], [Spark of Divinity].\nHe looked at the glowing runes.\n[Shadow Fragments: 0/200.]"
 p=vg.sistem_baglarini_bul(s,"Ada")
 assert ("Granite Guard",vg.DEGER,"Shadow Fragments\t0/200","[Shadow Fragments: 0/200.]") in p
 assert any(a=="Granite Guard" and r=="niteligi" and o=="Spark of Divinity" for a,r,o,e in p)
 assert not any(r=="rutbesi" for a,r,o,e in vg.sistem_baglarini_bul(s+"\nThe narrator changed topics.\nRank: Supreme.","Ada"))

def test_aspect_award_and_pending_rank_do_not_leak():
 s="[New Aspect acquired.]\n[Aspect Rank: Divine.]\nHe fell over.\n[Aspect Name: Star Walker.]\nInnate Ability: [Star Bond]."
 p=vg.sistem_baglarini_bul(s,"Ada")
 assert any(a=="Star Walker" and r=="rutbesi" and o=="Divine" for a,r,o,e in p)
 assert any(a=="Ada" and r=="yetenegi" and o=="Star Bond" for a,r,o,e in p)
 p=vg.sistem_baglarini_bul("[New Aspect acquired.]\n[Aspect Rank: Divine.]\nName: Boris.\nAspect: [Stone Shell].","Ada")
 assert not any(a=="Stone Shell" and r=="rutbesi" for a,r,o,e in p)

def test_all_existing_relations_have_roles():
 assert set(vg.ILISKI_ROLLERI)==set(vg.ILISKILER)
 assert all(x["subject_role"] and x["object_role"] for x in vg.ILISKILER.values())

def test_epistemic_reader_claims():
 assert k.epistemik_kontrol("Some people believed the Ivory Tower stood in the Tear.","believed") is None
 assert k.epistemik_kontrol("Some people believed the Ivory Tower stood in the Tear.","confirmed")
 assert k.epistemik_kontrol("Ada thought Boris was an ally.","believed")


def test_canonical_endpoints_precede_cross_aliases():
    evidence="Nila, the Oracle of the Night, arrived."
    marker=k.isaretle(evidence,"Nila","Oracle of the Night",{"Nila":["Oracle of the Night"]})
    assert "subject" in marker and "object" in marker
