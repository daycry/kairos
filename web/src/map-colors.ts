export interface CategoryGroup { key: string; project: string; category: string }

export const groupKey = (project: string, category: string): string => JSON.stringify([project, category]);

function hash(value: string): number {
  let result = 2166136261;
  for (const character of value) result = Math.imul(result ^ character.charCodeAt(0), 16777619);
  return result >>> 0;
}

/** Stable colors with perceptual separation between categories in one project. */
export function categoryColors(groups: CategoryGroup[]): Map<string, string> {
  const colors = new Map<string, string>();
  const projects = [...new Set(groups.map(group => group.project))].sort();
  for (const project of projects) {
    const categories = groups.filter(group => group.project === project).sort((a, b) => a.key.localeCompare(b.key));
    const used: number[] = [];
    const separation = Math.min(35, Math.floor(300 / Math.max(1, categories.length)));
    for (const group of categories) {
      let hue = hash(group.key) % 360;
      const distance = (candidate: number) => used.length ? Math.min(...used.map(other => Math.min(Math.abs(candidate - other), 360 - Math.abs(candidate - other)))) : 360;
      if (distance(hue) < separation) {
        let best = hue;
        for (let candidate = 0; candidate < 360; candidate++) if (distance(candidate) > distance(best)) best = candidate;
        hue = best;
      }
      used.push(hue);
      colors.set(group.key, `hsl(${hue}, 70%, 68%)`);
    }
  }
  return colors;
}
