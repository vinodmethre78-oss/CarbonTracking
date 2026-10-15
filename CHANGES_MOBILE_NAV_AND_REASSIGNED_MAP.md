# Mobile navigation overlap + reassigned-driver live map

## 1. Mobile drawer overlapping dashboard content
- `index.css`: new `--z-drawer-backdrop` (34) / `--z-drawer` (36) tokens; new `.sidebar-drawer`
  (inside `@media (max-width: 767.98px)` only) = near-opaque dark glass instead of the ~10% white fill.
- `DashboardLayout.jsx`: dark backdrop (click closes), drawer above it, top bar above both (X stays usable),
  scroll lock on `html`+`body` while open (restored on close/unmount), Escape + resize-to-desktop close,
  `h-dvh` + safe-area insets on mobile, floating AI button hidden under the drawer. Desktop unchanged.

## 2. Reassigned driver could not load the live map
- `models/db.py`: `Trip.to_dict(include_route=False)`; `route_polyline` is opt-in so list endpoints stay small.
- `routes/driver.py`: `GET /driver/active-trip` returns `route_polyline`; the impossible-GPS-jump check and the
  destination lock now only consider pings from the trip's *current* driver.
- `NewTrip.jsx`: active trip (incl. stored route) restored into `routeOptions/chosenRouteIdx`; one 8 s visibility-aware
  poll detects a trip assigned to / removed from this driver; original driver is detached cleanly (403 ping -> re-check);
  map `trip` dep -> `trip?.id`; live-position effect re-runs when the map becomes ready.
- `offlineQueue.js`: pings rejected with 403/404 are dropped instead of retried forever.
- `tests/test_reassignment.py`: 5 new tests (`TestReassignedDriverLiveMap`).
