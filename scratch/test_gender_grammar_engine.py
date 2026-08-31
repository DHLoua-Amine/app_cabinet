import sys
import re

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def _apply_gender_grammar_corrections(text: str) -> str:
    if not text:
        return text
    
    res = text

    # Check if Party 2 is female (e.g. الطرف الثاني المشترية / الموهوب لها / السيدة / وفاء)
    p2_is_female = bool(re.search(
        r"الطرف\s*الثاني\s*(المشترية|الموهوب\s*لها|المتنازل\s*لها|المكترية|الزوجة|السيدة)",
        res
    ))

    # Check if Party 1 is female (e.g. الطرف الأول البائعة / الواهبة / المتنازلة / السيدة)
    p1_is_female = bool(re.search(
        r"الطرف\s*الأول\s*(البائعة|الواهبة|المتنازلة|المؤجرة|الزوجة|السيدة)",
        res
    ))

    if p2_is_female:
        # Replace male verbs/relative pronouns for Party 2 with female forms across the contract text
        res = re.sub(r"\b(ل?لطرف\s*الثاني)\s*الذي\s*قبل\b", r"\1 التي قبلت", res)
        res = re.sub(r"\b(ل?لطرف\s*الثاني)\s*الذي\s*اشترى\b", r"\1 التي اشترت", res)
        res = re.sub(r"\b(ل?لطرف\s*الثاني)\s*الذي\s*تسلم\b", r"\1 التي تسلمت", res)
        res = re.sub(r"\b(ل?لطرف\s*الثاني)\s*الذي\s*عاوض\b", r"\1 التي عاوضت", res)
        res = re.sub(r"\b(ل?لطرف\s*الثاني)\s*الذي\s*اسقط\b", r"\1 التي اسقطت", res)
        res = re.sub(r"\b(فائدة|لفائدة)\s*الطرف\s*الثاني\s*الذي\b", r"\1 الطرف الثاني التي", res)

    if p1_is_female:
        # Replace male action verbs for Party 1 with female forms
        res = re.sub(r"\bباع\s*واحال\s*الطرف\s*الأول\b", "باعت واحالت الطرف الأول", res)
        res = re.sub(r"\bوهب\s*وسلم\s*وحوز\s*الطرف\s*الأول\b", "وهبت وسلمت وحوزت الطرف الأول", res)
        res = re.sub(r"\bعاوض\s*وسلم\s*الطرف\s*الأول\b", "عاوضت وسلمت الطرف الأول", res)
        res = re.sub(r"\bتنازل\s*واسقط\s*الطرف\s*الأول\b", "تنازلت واسقطت الطرف الأول", res)

    return res


# Test cases
t1 = "الطرف الثاني المشترية: السيدة: وفاء بنت حسن... اتفاقا على: الفصل الأول: وهبت وسلمت وحوزت الطرف الأول تحت سائر الضمانات للطرف الثاني الذي قبل جميع مناباتها"
cleaned = _apply_gender_grammar_corrections(t1)

print("INPUT:  ", t1)
print("\nOUTPUT: ", cleaned)

assert "للطرف الثاني التي قبلت" in cleaned
print("\n[SUCCESS] Gender Grammar Engine verified with 0 errors!")
