import { Link } from '@tanstack/react-router';
import { ArrowRight, LayoutDashboard, TriangleAlert, GitCompareArrows, LockKeyhole } from 'lucide-react';
const steps = [
 { path: '/', label: 'Monitor operations', icon: LayoutDashboard },
 { path: '/disruptions', label: 'Report & assess', icon: TriangleAlert },
 { path: '/compare', label: 'Compare & approve', icon: GitCompareArrows },
] as const;
export function WorkflowNavigation({ current }: { current: '/' | '/disruptions' | '/compare' }) {
 return <nav className="workflow-nav" aria-label="Replanning workflow">{steps.map((step,i)=><div key={step.path}><Link to={step.path} aria-current={current===step.path?'step':undefined} className={current===step.path?'current':''}><step.icon size={15}/><span>{step.label}</span></Link>{i<steps.length-1&&<ArrowRight size={13} className="workflow-arrow"/>}</div>)}<span className="workflow-safety"><LockKeyhole size={12}/> Approval required before dispatch</span></nav>;
}
