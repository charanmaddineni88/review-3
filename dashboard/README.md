# Dashboard

The dashboard should consume the live API and websocket outputs to visualize detection, environment, risk, alerts, and forecast data without inventing measurement values.

## Dashboard responsibilities

- show system health and provider state;
- show live or recent detection results;
- display environmental readings with freshness labels;
- render risk and alert history;
- display map context and short-term forecast overlays;
- clearly indicate unavailable or stale data states.

## Data policy

The frontend must never silently replace missing or stale live data with demo values. Any display of demo mode should be explicitly labeled in the UI.

## Live map (NASA GIBS map)

The Live Map and Spread Prediction pages render a keyless Leaflet map on NASA GIBS imagery (`src/components/LiveMap.jsx`), showing:
- the active fire event marker + an area circle sized from its visual-area proxy, when a real event exists;
- live NASA FIRMS satellite hotspots as markers, when configured;
- a wind vector drawn from the current live weather reading.

