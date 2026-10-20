import React from 'react'
import {createRoot} from 'react-dom/client'
import Console from './Console'
import './style.css'
createRoot(document.getElementById('root')!).render(<React.StrictMode><Console/></React.StrictMode>)
