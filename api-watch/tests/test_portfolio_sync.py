import json,tempfile
from pathlib import Path
from django.test import SimpleTestCase
from watchtower.portfolio_sync import build_metadata,sync,API
class PublicPortfolioTests(SimpleTestCase):
 def test_only_public_selected_project_and_article_fields_are_exported(self):
  profile={'profile':{'email':'never-copy@example.com'},'private':{'answers':'NEVER_COPY'},'activities':[{'projects':[{'id':'project','title':'Public','summary':'검증할 공개 설명','links':[{'url':'javascript:bad()'}]}]}]}
  index=[{'id':'specific','activity':'project','title':'갱신한 제목','oneliner':'공개 요약','stack':['Python'],'post':'public-story'}]
  data=build_metadata(profile,index,[('content/posts/note-ai-trend-14.md',{'series':'ai-trend','episode':14,'title':'소형 모델','date':'2026-11-16','summary':'공개 요약'})],'a'*40,'2026-11-17T00:00:00Z')
  self.assertNotIn('never-copy',json.dumps(data));self.assertNotIn('NEVER_COPY',json.dumps(data));self.assertEqual(data['projects'][0]['title'],'갱신한 제목');self.assertEqual(data['projects'][0]['stack'],['Python']);self.assertEqual(data['learning_notes'][0]['episode'],14);self.assertTrue(data['links']['preparation'].endswith('/study/index.html'))
 def test_source_revision_is_pinned_and_unchanged_revision_skips_source_downloads(self):
  calls=[];sha='a'*40;tree='b'*40
  def fetch(url):
   calls.append(url)
   if url==API+'/commits/main':return json.dumps({'sha':sha,'commit':{'tree':{'sha':tree},'committer':{'date':'2026-11-17T00:00:00Z'}}})
   if '/git/trees/'in url:return json.dumps({'tree':[{'path':'content/posts/2026-ai-trend-14.md','type':'blob'},{'path':'content/private/secret.json','type':'blob'},{'path':'docs/study/notes/js_basic_syntax_2.html','type':'blob'},{'path':'docs/study/notes/js_controlling_event.html','type':'blob'}]})
   self.assertIn('/'+sha+'/',url)
   if url.endswith('data/portfolio.yaml'):return 'activities:\n- projects:\n  - id: demo\n    title: Public\n    summary: Public summary\n'
   if url.endswith('data/projects_index.yaml'):return '[]'
   return '---\nseries: ai-trend\nepisode: 14\ntitle: Small models\ndate: "2026-11-16"\nsummary: Public\n---\n'
  with tempfile.TemporaryDirectory()as d:
   p=Path(d)/'portfolio.json';first=sync(p,fetcher=fetch);self.assertEqual(len(first['learning_notes']),1);self.assertEqual(first['study']['note_count'],2);self.assertEqual(len(first['study']['highlights']),2);self.assertFalse(any('private/'in u for u in calls));calls.clear();sync(p,fetcher=fetch);self.assertEqual(calls,[API+'/commits/main']);before=p.read_text()
   def broken(url):
    if url==API+'/commits/main':return fetch(url)
    raise OSError('source unavailable')
   with self.assertRaises(OSError):sync(p,fetcher=broken,force=True)
   self.assertEqual(p.read_text(),before)

 def test_distinct_projects_do_not_inherit_an_unrelated_parent_repository(self):
  profile={'activities':[{'projects':[{'id':'ssafy','title':'Parent','summary':'Parent','links':[{'url':'https://github.com/0Ju12/thread-only'}]}]}]}
  items=[{'id':'vqa','activity':'ssafy','title':'VQA','post':'vqa-story'},{'id':'thread','activity':'ssafy','title':'Thread','post':'thread-story','links':[{'url':'https://github.com/0Ju12/thread-only'}]}]
  data=build_metadata(profile,items,[],'a'*40,'2026-11-17T00:00:00Z');vqa=next(p for p in data['projects']if p['id']=='vqa');self.assertNotIn('thread-only',json.dumps(vqa));self.assertTrue(vqa['repository'].endswith('/posts/vqa-story.html'))
