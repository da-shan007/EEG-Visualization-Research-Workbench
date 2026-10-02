import './styles.css';
import { generateSyntheticDataset } from './data/eegData.js';
import { WorkbenchApp } from './components/WorkbenchApp.js';

const dataset = generateSyntheticDataset();
const root = document.getElementById('root');
root.innerHTML = '';
root.appendChild(WorkbenchApp(dataset));
