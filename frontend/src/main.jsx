import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

// Note: StrictMode is intentionally NOT used here. React 18/19's StrictMode
// double-mounts components in development to catch bugs, but Leaflet's internal
// DOM position cache (_leaflet_pos) doesn't handle that cleanly during zoom
// animations, causing "Cannot read properties of undefined (reading '_leaflet_pos')".
// This is a known react-leaflet + StrictMode incompatibility, not a bug in our code.
createRoot(document.getElementById('root')).render(<App />)

