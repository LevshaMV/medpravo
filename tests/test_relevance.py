import unittest
import relevance

class ScopeTests(unittest.TestCase):
 def test_real_noise_is_excluded_even_when_appendix_mentions_medicine(self):
  bad=[
   'Постановление о строительстве школ и детских садов',
   'Правительство расширило развитие детско-юношеского спорта',
   'Приказ Минюста об учетной политике центрального аппарата',
   'Федеральный закон об адвокатской деятельности и адвокатуре',
   'О сведениях о доходах, об имуществе сотрудников ФНС',
   'О создании экспертного совета по налогам крупнейших налогоплательщиков',
   'Правительство РФ выделило Республике Тыва деньги на закупку медицинского оборудования',
   'О льготах ветеранам боевых действий по налогам на имущество',
   'Об утверждении форм сообщений о страховании жизни',
   'О лицензировании образовательной деятельности',
   'Об открытии автомобильного пункта пропуска',
   'Постановление о межевании улицы']
  for title in bad:
   with self.subTest(title=title):self.assertEqual(relevance.evaluate(title,'Медицинские организации, персональные данные, дети, налог, ОМС',{'id':'government'})['relevance'],'other')
 def test_confirmed_tasks_and_general_employer_rules_are_kept(self):
  good=[
   'Об утверждении тарифного соглашения в сфере ОМС в Калужской области',
   'О порядке оказания медицинской помощи детям',
   'О радиационной безопасности при проведении КТ',
   'О применении контрастных препаратов при МРТ',
   'Об утверждении порядка анестезиологии и реанимации',
   'О медицинской помощи в условиях дневного стационара',
   'Об обращении медицинских изделий',
   'О безопасности аппаратов Siemens Magnetom Harmony',
   'Об отзыве аппарата Toshiba Aquilion 64',
   'О защите персональных данных пациентов',
   'Об изменении Трудового кодекса Российской Федерации',
   'О переносе выходных дней в 2027 году',
   'О применении контрольно-кассовой техники',
   'О применении упрощенной системы налогообложения',
   'О профессиональном стандарте врача анестезиолога']
  for title in good:
   with self.subTest(title=title):self.assertEqual(relevance.evaluate(title,'',{'id':'government'})['relevance'],'medical')
 def test_children_alone_are_not_a_medical_topic(self):
  self.assertEqual(relevance.evaluate('Об изменении пособий семьям с детьми','',{'id':'government'})['relevance'],'other')
  self.assertNotIn('Дети',relevance.evaluate('Об изменении пособий семьям с детьми','',{'id':'government'})['topics'])
 def test_missing_subject_is_separate_not_assumed_medical(self):
  for sid in ('minzdrav','pravo','roszdrav'):
   self.assertEqual(relevance.evaluate('Приказ № 25 от 14.10.2026','',{'id':sid,'medical':sid!='pravo'})['relevance'],'review')
 def test_oms_source_keeps_broad_oms_but_not_internal_staff_rules(self):
  self.assertEqual(relevance.evaluate('Дополнительное соглашение № 3','',{'id':'tfoms'})['relevance'],'medical')
  self.assertEqual(relevance.evaluate('Приказ о служебном поведении гражданских служащих центрального аппарата','',{'id':'ffoms'})['relevance'],'other')
 def test_clinical_profile_matches_specialties_not_every_field(self):
  self.assertEqual(relevance.evaluate('Клинические рекомендации: Артериальная гипертензия · Дети','',{'id':'clinrec'})['relevance'],'medical')
  self.assertEqual(relevance.evaluate('Клинические рекомендации: Зубные протезы · Взрослые','',{'id':'clinrec'})['relevance'],'other')
 def test_issuing_ministry_is_not_medical_subject(self):
  for title in ['Приказ Министерства здравоохранения Российской Федерации «О признании утратившими силу приказов»', 'Приказ Федеральной службы по надзору в сфере защиты прав потребителей и благополучия человека «О внесении изменений в приказ от 2025 года»']:
   with self.subTest(title=title):self.assertNotEqual(relevance.evaluate(title,'',{'id':'minzdrav','medical':True})['relevance'],'medical')
  self.assertEqual(relevance.evaluate('Приказ Министерства здравоохранения Российской Федерации «О порядке оказания медицинской помощи»','',{'id':'minzdrav'})['relevance'],'medical')
 def test_actual_retained_noise_has_no_place_in_main_feed(self):
  for title in ['Об утверждении Положения о министерстве здравоохранения Калужской области','График личного приёма граждан Министром здравоохранения','Приказ Министерства здравоохранения о главных внештатных специалистах','План научно-практических мероприятий Министерства здравоохранения на 2026 год','Автоматизированная система Сведения о медицинских изделиях','О границах санитарной охраны курортов Анапы и Сочи']:
   with self.subTest(title=title):self.assertEqual(relevance.evaluate(title,'',{'id':'minzdrav','medical':True})['relevance'],'other')
 def test_unsupported_disease_subspecialties_go_to_manual_review(self):
  for title in ['Клинические рекомендации: Сахарный диабет: ретинопатия и макулярный отёк','Клинические рекомендации: Доброкачественные опухоли век и конъюнктивы','Клинические рекомендации: Трансплантация печени','Клинические рекомендации: TRAPS — синдром некроза опухоли']:
   with self.subTest(title=title):self.assertEqual(relevance.evaluate(title,'',{'id':'clinrec'})['relevance'],'review')

if __name__=='__main__':unittest.main()
