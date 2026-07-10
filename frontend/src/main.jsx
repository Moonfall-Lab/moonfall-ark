import React, { useState, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import Landing from './components/Landing.jsx'
import './index.css'

function Router() {
  const [route, setRoute] = useState(window.location.hash)

  useEffect(() => {
    const onHash = () => setRoute(window.location.hash)
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const handleEnter = () => {
    window.location.hash = '#/dashboard'
  }

  if (route === '#/dashboard') {
    return <App />
  }

  return <Landing onEnter={handleEnter} />
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <Router />
  </React.StrictMode>,
)
