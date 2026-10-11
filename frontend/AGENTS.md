<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.
<!-- LOVABLE:END -->

## Application architecture
- Keep ReRoute content in TanStack file routes with a shared application shell; this preserves deep links and consistent navigation.
- Keep frontend operational views disconnected until a real service is supplied; never seed, persist, or fabricate operational records.
- Load Leaflet dynamically after hydration and use it only for a geographic basemap until verified location data is supplied; this keeps SSR browser-safe and prevents false tracking claims.
- Use shared frontend forms and record-table views with explicit service-dependent unavailable states; validation must never imply persistence or successful optimization.
- Prebundle shared dialog and slot dependencies alongside the template's React optimizer entries; this avoids late dependency discovery mixing React instances in an already-open preview.
