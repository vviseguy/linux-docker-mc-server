import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './ui/App'
import { Toaster } from 'sonner'
import './ui/styles.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
        <App />
    </React.StrictMode>
)

// Mount the global toaster outside the app tree
const toasterEl = document.getElementById('toaster-root')
if (toasterEl) {
    ReactDOM.createRoot(toasterEl).render(<Toaster richColors position="top-right" />)
}
