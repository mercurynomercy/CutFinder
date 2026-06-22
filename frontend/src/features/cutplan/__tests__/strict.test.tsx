import { StrictMode } from 'react'
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/mocks/server'
import { CutplanPage } from '@/features/cutplan/index'

const API = 'http://localhost:5080/api'
const PLAN = { shots:[{clip_id:1,roll:'a',in_s:0,out_s:12,content:'x',rationale:'y',chapter:'开场',clip_label:'A-0001.mov',thumb_ref:'/api/clips/1/thumbnail'}], chapters:['开场'], total_s:12, target_min_s:null,target_max_s:null,within_target:true,note:'',markdown:'md' }

describe('strict', () => {
  it('restores under StrictMode', async () => {
    localStorage.setItem('cutfinder:cut-active-session','1')
    server.use(
      http.get(`${API}/cut/sessions`, () => HttpResponse.json({ sessions:[{id:1,title:'t',status:'idle',created_at:null,updated_at:null}] })),
      http.get(`${API}/cut/sessions/1`, () => HttpResponse.json({ session:{id:1,title:'t',status:'idle',created_at:null,updated_at:null}, messages:[{role:'assistant',content:'已生成',created_at:null}], plan:PLAN })),
    )
    render(<StrictMode><CutplanPage onClose={()=>{}} /></StrictMode>)
    expect(await screen.findByText('A-0001.mov')).toBeInTheDocument()
    localStorage.clear()
  })
})
