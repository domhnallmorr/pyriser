import numpy as np
import pandas as pd

def convert_to_number(s, return_none=False, return_np_nan=False):
	if return_none == True and return_np_nan == True:
		raise Exception("Cannot return both return_none and return_np_nan")
		
	try:
		float(s)
		return float(s)
	except ValueError:
		if return_none:
			return None
		elif return_np_nan:
			return np.nan
		else:
			return s

class DPX:
	"""
	Description:
	-------------
		- 
		
	Author:
	-------------
		- Domhnall Morrisey 31/05/2021
		
	Prerequisites:
	-------------
		- Python > 3.6

	Limitations: 
	-------------


	Key Variables: 
	-------------

		
	TO DO: 
	-------------
		- Add cement checks to Riser component
			-sheared, 0 axial stiffness
		- Add check for current units (should all be the same)
		- Add check for auxillary line config/pressures (identify unique configs)
		- Extract current profiles
	"""
	def __init__(self, dpx, verbose=False):
		self.dpx = dpx
		self.verbose = verbose
		self.default_lines = ['Choke', 'Kill', 'Mud Booster', 'Hydraulic']
		
		self.read_das()
		self.parse_dpx()
		
	def read_das(self):
		if self.verbose:
			print('reading DPX')
		with open(self.dpx) as f:
			self.data = f.readlines()
			
	def parse_dpx(self):
		name = None
		component_type = None
		menu = None
		in_stackup = False
		self.components = {}
		
		for d in self.data:

			if d.startswith("<component "):
				d = d.split('"')
				name = d[1]
				component_id = d[3]
				component_type = d[-2]
				self.components[name] = DPXComponent(name, component_id, component_type, self)

			elif d.startswith('<menu '):
				menu = d.split('"')[1]
				self.components[name].menus[menu] = []
				current_row = -1
				
			elif d.startswith('<option '):
				d = d.split('"')
				param = d[1]
				value = convert_to_number(d[-2])
				self.components[name].options[param] = value
				
			elif menu and d.startswith('<value '):
				d = d.split('"')
				param = d[1]
				value = convert_to_number(d[-1].split('<')[0].replace('>', ''))
				row = int(d[3])
				if row != current_row:
					self.components[name].menus[menu].append({})
					current_row = row
				self.components[name].menus[menu][-1][param] = value

	def get_all_components(self, component_type): 
		return [self.components[x].name for x in self.components.keys() if self.components[x].component_type == component_type]

	def find_id(self, component_id):
		'''
			loops over all components and attempts to find the component with the id passed through to this method
		'''
		
		name = None
		for c in self.components:
			if self.components[c].component_id == component_id:
				return self.components[c].name
				break
		if not name:
			return name

	def assemble_joint_weights(self):
		weight_data = []
		joints = self.get_all_components('Drilling Riser Joint')
		for b in self.get_all_components('BOP'):
			joints.append(b)
			
		for joint in joints:
			dry_weight = None
			wet_weight = None
			
			if 'Drilling Riser Joint - Properties|||' in self.components[joint].menus.keys():
				dry_weight = self.components[joint].menus['Drilling Riser Joint - Properties|||'][-1]['Weight in Air - W(air)']
				wet_weight = self.components[joint].menus['Drilling Riser Joint - Properties|||'][-1]['Weight in Water - W(water)']
			elif 'Properties - Define |||' in self.components[joint].menus.keys():
				dry_weight = self.components[joint].menus['Properties - Define |||'][-1]['Weight in Air']
				wet_weight = self.components[joint].menus['Properties - Define |||'][-1]['Weight in Water']
				
			weight_data.append([joint, dry_weight, wet_weight])
			
		return weight_data
		
	def assemble_load_sharing_data(self):
		'''
			Loops over all drilling riser joints in the DPX and returns a list with their title, load sharing on/off and gap setting
		'''
		load_sharing_data = []
		joints = self.get_all_components('Drilling Riser Joint')
		for joint in joints:
			load_sharing_data.append([joint, self.components[joint].menus['Drilling Riser Joint - Properties|||'][-1]['Load Sharing with Choke/Kill Line'],
				self.components[joint].menus['Drilling Riser Joint - Properties|||'][-1]['Load Sharing Gap']])
				
			if load_sharing_data[-1][1] not in ['Yes', 'No']:
				load_sharing_data[-1][1] = 'No'
			if load_sharing_data[-1][2] == '':
				load_sharing_data[-1][2] = 0.0
				
		return load_sharing_data

	def assemble_tensioner_data(self):
		tensioner_data = {}
		tensioners = self.get_all_components('Tensioner')
		
		for tensioner in tensioners:
			recoil_type = None
			arv_curve = [[], []]
			if "Tensioner Recoil Type - Options|||" in self.components[tensioner].options.keys():
				recoil_type = self.components[tensioner].options['Tensioner Recoil Type - Options|||']
				
			if recoil_type == "Detailed Hydro-Pneumatic":
				if "Anti-Recoil Valve - Closure Curve |||" in self.components[tensioner].menus.keys():
					for row in self.components[tensioner].menus["Anti-Recoil Valve - Closure Curve |||"]:
						arv_curve[0].append(row["Cylinder Stroke"])
						arv_curve[1].append(row["Valve Closure"])
						
			tensioner_data[tensioner] = {
										"Recoil Type": recoil_type,
										"ARV Curve": arv_curve,
										}
		return tensioner_data
		
	def assemble_riser_tensioner_components(self):
		'''
			Get the tensioner component assigned to each riser component in the model
		'''
		riser_tensioner_data = []
		risers = self.get_all_components('Drilling Riser')
		
		for riser in risers:
			tensioner = None
			tensioner_type = None
			recoil_type = None
			tensioner_line_length_zero_stroke = None
			
			if 'DR Storage Menu|||' in self.components[riser].menus.keys():
				menu = self.components[riser].menus['DR Storage Menu|||']
				for row in menu:
					if 'Tensioner' in row.keys():
						if self.find_id(row['Tensioner']) in self.components.keys():
							tensioner = self.find_id(row['Tensioner'])
							
							if 'Tensioner Type - Options|||' in self.components[tensioner].options.keys():
								tensioner_type = self.components[tensioner].options['Tensioner Type - Options|||']
							if 'Tensioner Recoil Type - Options|||' in self.components[tensioner].options.keys():
								recoil_type = self.components[tensioner].options['Tensioner Recoil Type - Options|||']
								
							if 'Tensioner Cylinder Properties - Hydro-Pneumatic - Wireline|||' in self.components[tensioner].menus.keys():
								menu = self.components[tensioner].menus['Tensioner Cylinder Properties - Hydro-Pneumatic - Wireline|||']
								
								if 'Tensioner Line Length at Zero Stroke' in menu[0].keys():
									tensioner_line_length_zero_stroke = menu[0]['Tensioner Line Length at Zero Stroke']
					
				riser_tensioner_data.append([riser, tensioner, tensioner_type, recoil_type, tensioner_line_length_zero_stroke])
						
		return riser_tensioner_data
		
	def assemble_riser_gooseneck_data(self):
		gooseneck_data = []
		risers = self.get_all_components('Drilling Riser')
		
		for riser in risers:
			joint = None
			length_along_joint = None
			
			if 'Drilling Riser Gooseneck Location|||' in self.components[riser].menus.keys():
				menu = self.components[riser].menus['Drilling Riser Gooseneck Location|||'][-1]
				joint = menu["Joint"]
				length_along_joint = menu["Length along Joint"]
			
			gooseneck_data.append([riser, joint, length_along_joint])
			
		return gooseneck_data
		
	def assemble_riser_soil_components(self):
		riser_soil_data = []
		risers = self.get_all_components('Drilling Riser')
		
		for riser in risers:
			soil_profile = None
			
			if "Soil Structure|||" in self.components[riser].menus.keys():
				menu = self.components[riser].menus["Soil Structure|||"][-1]
				if "Soil Structure Model" in menu.keys():
					soil_profile = self.find_id(menu["Soil Structure Model"])
				
			riser_soil_data.append([riser, soil_profile])

		return riser_soil_data
		
	def assemble_riser_cement_data(self):
		cement_data = []
		risers = self.get_all_components('Drilling Riser')
		
		for riser in risers:
			if 'Cement Options|||' in self.components[riser].menus.keys():
				menu = self.components[riser].menus['Cement Options|||'][-1]
				cement_data.append([riser, menu['Cement Level'], menu['Cement Setting'],  menu['Pipe-In-Pipe Lateral Stiffness'],
							menu['Pipe-In-Pipe Axial Stiffness (Bonded)'], menu['Power Law Exponent (Cement Shortfall)']])
			else:
				cement_data.append([riser, None, None, None, None, None])
		return cement_data
	
	def assemble_riser_drilling_mud_flow_parameters(self):
		mud_data = []
		risers = self.get_all_components('Drilling Riser')
		
		for riser in risers:
			if 'Drilling Mud Flow Model  -  Parameters|||' in self.components[riser].menus.keys():
				menu = self.components[riser].menus['Drilling Mud Flow Model  -  Parameters|||'][-1]
				mud_data.append([riser, menu['Target Finite Volume Length'], menu['Fanning Friction Factor'],  menu['Discharge Coefficient (Outflow)'],
							menu['Discharge Coefficient (Inflow)'], menu['Atmospheric Pressure']])
			else:
				mud_data.append([riser, None, None, None, None, None])
		return mud_data		
		
	def assemble_conductor_casing_joint_data(self):
		conductor_casing_data = []
		joints = self.get_all_components('Conductor-Casing')
		
		for joint in joints:
			
			if 'Properties Detailed - Define|||' in self.components[joint].menus.keys(): #Handle if conductor not defined
				menu2 = self.components[joint].menus['Properties Detailed - Define|||'][-1]
				cond_od = menu2['External Diameter, Do']
				cond_id = menu2['Internal Diameter, Di']
				cond_wt = round((cond_od-cond_id)/2, 3)
				cond_mat = self.find_id(menu2['Material'])
				cond_fluid = menu2['Conductor Internal Fluid']
			else:
				cond_od = np.nan
				cond_wt = np.nan
				cond_mat = np.nan
				cond_fluid = np.nan

			if 'Surface Casing - Define|||' in self.components[joint].menus.keys(): #Handle if conductor not defined
				menu2 = self.components[joint].menus['Surface Casing - Define|||'][-1]
				cas_od = convert_to_number(menu2['External Diameter, Do'], return_np_nan=True)
				cas_id = convert_to_number(menu2['Inner Diameter, Di'], return_np_nan=True)
				if np.isnan(cas_od) or np.isnan(cas_od): #handle if no casing defined
					cas_wt = np.nan
				else:
					cas_wt = round((cas_od-cas_id)/2, 3)
					
				cas_mat = self.find_id(menu2['Surface Casing Material'])
				cas_fluid = menu2['Surface Casing Internal Fluid']
				cas_cement = self.find_id(menu2['Cement Material'])
			else:
				cas_od = np.nan
				cas_wt = np.nan
				cas_mat = np.nan
				cas_fluid = np.nan
				cas_cement = np.nan
				
			if 'Drilled And Grouted Bore Hole Properties|||' in self.components[joint].menus.keys():
				menu3 = self.components[joint].menus['Drilled And Grouted Bore Hole Properties|||'][-1]
				hole_od = menu3['Bore Hole Diameter']
			else:
				hole_od = 0.0
				
			if 'Sheared Cement Options|||' in self.components[joint].menus.keys():
				menu1 = self.components[joint].menus['Sheared Cement Options|||'][-1]
				sheared_cement = menu1['Sheared Cement Option']
			else:
				sheared_cement = None
				
			conductor_casing_data.append([joint, sheared_cement, self.components[joint].options['Conductor Casing Installation Options|||'],
					cond_od, cond_wt, cond_mat, cond_fluid, cas_od, cas_wt, cas_mat, cas_fluid, cas_cement, hole_od])
		
		return conductor_casing_data

	def assemble_fluid_data(self):
		fluid_data = []
		fluids = self.get_all_components('Drilling Mud')
		
		for fluid in fluids:
			menu = self.components[fluid].menus['Drilling Mud Properties|||'][-1]
			fluid_data.append([fluid, convert_to_number(menu['Mass Density']), convert_to_number(menu['Internal Pressure'], return_none=True), convert_to_number(menu['Bulk Modulus'], return_np_nan=True),])

		return fluid_data
	
	def assemble_internal_fluid_load_case_data(self):
		load_case_data = []
		load_cases = self.get_all_components('Internal Fluid Load Case')
		# first get all the unique auxillary lines
		aux_lines = {}
		default_lines = {0: 'Choke', 1: 'Kill', 2: 'Mud Booster', 3: 'Hydraulic'}
		
		for lc in load_cases:
			local_lines = []
			pressures = []
			
			if 'Auxiliary Line Properties - Define|||' in self.components[lc].menus.keys():
				menu = self.components[lc].menus['Auxiliary Line Properties - Define|||']
				for idx, row in enumerate(menu):
					aux_line = row['Auxiliary Line']
					if row["Pressure"] != "":
						pressures.append(row["Pressure"])
					else:
						pressures.append(np.nan)
					
					#Handle empty string, default line
					if aux_line == '':
						aux_line = default_lines[idx]
						
					#if aux_line not in local_lines:
					local_lines.append(aux_line)
				
				renamed_local_lines = [] #will add (1), (2), to the end of each line as required
				
				for idx, line in enumerate(local_lines):
					if local_lines.count(line) != 1:
						#print(local_lines[:idx+1])
						count = local_lines[:idx+1].count(line)
						renamed_local_lines.append(f'{line} ({count})')
					else:
						renamed_local_lines.append(f'{line} (1)')

				# Add the lines to the aux_lines dict, default values of NOne for each load case
				
				for idx, line in enumerate(renamed_local_lines):
					if line not in aux_lines.keys():
						aux_lines[line] = {lc: np.nan for lc in load_cases}
					aux_lines[line][lc] = pressures[idx]
		
		for lc in load_cases:
			menu = self.components[lc].menus['Internal Fluids - Define|||'][-1]
			
			if 'Internal Fluid - Level Above Keel|||' in self.components[lc].menus.keys():
				level_above_keel = self.components[lc].menus['Internal Fluid - Level Above Keel|||'][-1]['Level Above Keel']
				if str(level_above_keel).lower() == 'default':
					level_above_keel = np.nan
			else:
				level_above_keel = np.nan
			load_case_data.append([lc, menu['Internal Fluid'], menu['Fluid Level'], level_above_keel])
		
			for aux_line in aux_lines.keys():
				load_case_data[-1].append(aux_lines[aux_line][lc])
				
		return load_case_data, list(aux_lines.keys())

	def assemble_current_data(self):
		current_data = []
		currents = self.get_all_components('Current')
		
		for current in currents:
			if 'Current - Piecewise Linear|||' in self.components[current].menus.keys():
				surface_current = self.components[current].menus['Current - Piecewise Linear|||'][0]['Velocity']
			else:
				surface_current = 0
			#menu = self.components[current].menus['Drilling Mud Properties|||'][-1]
			current_data.append([current, self.components[current].options['Current Type|||'], self.components[current].options['Current Speed Units|||'],
							surface_current])

		return current_data		

	def assemble_current_profiles(self):
		depths = []
		currents = self.get_all_components('Current')
		for current in currents:
			if 'Current - Piecewise Linear|||' in self.components[current].menus.keys():
				for row in self.components[current].menus['Current - Piecewise Linear|||']:
					depth = row['Distance Below Mean Waterline']
					if depth not in depths:
						depths.append(depth)
		
		df = pd.DataFrame(index=sorted(depths), columns=currents)
		
		for current in currents:
			if 'Current - Piecewise Linear|||' in self.components[current].menus.keys():
				for row in self.components[current].menus['Current - Piecewise Linear|||']:
					depth = row['Distance Below Mean Waterline']
					df[current][depth] = row['Velocity']
		
		df.insert(0, 'Depth', df.index)

		return df.values.tolist(), currents

	def assemble_wave_types(self):
		wave_data = []
		waves = self.get_all_components('Wave')
		
		for wave in waves:
			wave_type = 'Unknown' # default

			if 'Regular Airy|||' in self.components[wave].menus.keys():
				wave_type = 'Regular Airy'
			elif 'Jonswap - Equal Area - Hs/Tp|||':
				wave_type = 'Jonswap - Equal Area - Hs/Tp'
				
			wave_data.append([wave, wave_type])
		return wave_data
		
	def assemble_regular_wave_data(self):
		wave_data = []
		waves = self.assemble_wave_types()
		
		for wave in waves:
			if wave[1] == 'Regular Airy':
				amp = self.components[wave[0]].menus['Regular Airy|||'][-1]['Amplitude']
				period = self.components[wave[0]].menus['Regular Airy|||'][-1]['Wave Period']
				direction = self.components[wave[0]].menus['Regular Airy|||'][-1]['Direction']
				
				wave_data.append([wave[0], amp, period, direction])
				
		return wave_data
		
	def assemble_jonswap_wave_data(self):
		wave_data = []
		waves = self.assemble_wave_types()
		
		for wave in waves:
			if wave[1] == 'Jonswap - Equal Area - Hs/Tp':
				wave_height = self.components[wave[0]].menus['Jonswap - Equal Area - Hs/Tp|||'][-1]['Wave Height']
				period = self.components[wave[0]].menus['Jonswap - Equal Area - Hs/Tp|||'][-1]['Peak Period']
				freq_increment = self.components[wave[0]].menus['Jonswap - Equal Area - Hs/Tp|||'][-1]['Max Frequency Increment']
				cutoff_freq = self.components[wave[0]].menus['Jonswap - Equal Area - Hs/Tp|||'][-1]['Cut-off Frequency']
				no_harmnonics = self.components[wave[0]].menus['Jonswap - Equal Area - Hs/Tp|||'][-1]['Number of Harmonics']
				wave_dir = self.components[wave[0]].menus['Jonswap - Equal Area - Hs/Tp|||'][-1]['Wave Directions']
				dominant_dir = self.components[wave[0]].menus['Jonswap - Equal Area - Hs/Tp|||'][-1]['Dominant Direction']
				wave_spreading_exp = self.components[wave[0]].menus['Jonswap - Equal Area - Hs/Tp|||'][-1]['Wave Spreading Exponent']
				
				wave_data.append([wave[0], wave_height, period, freq_increment, cutoff_freq, no_harmnonics, wave_dir, dominant_dir, wave_spreading_exp])
				
		return wave_data

	def assemble_wind_data(self):
		wind_data = []
		winds = self.get_all_components('Wind')
		
		
		for wind in winds:
			speed = self.components[wind].menus['Wind Data|||'][-1]['Mean Wind Speed']
			direction = self.components[wind].menus['Wind Data|||'][-1]['Mean Wind Direction']
			units = self.components[wind].options['Imperial Units Options|||']
			
			wind_data.append([wind, speed, direction, units])
				
		return wind_data

	def assemble_environmental_load_case_data(self):
		env_lc_data = []
		env_lcs = self.get_all_components('Environmental Load Case')
		for env_lc in env_lcs:
			current = 'None'
			wave = 'None'
			wind = 'None'
			
			if 'Env Load Case - Current Choice|||' in self.components[env_lc].menus.keys():
				current = self.find_id(self.components[env_lc].menus['Env Load Case - Current Choice|||'][-1]['Current'])
			if 'Env Load Case - Wave Choice|||' in self.components[env_lc].menus.keys():
				wave = self.find_id(self.components[env_lc].menus['Env Load Case - Wave Choice|||'][-1]['Wave'])
			if 'Env Load Case - Wind Choice|||' in self.components[env_lc].menus.keys():
				wind = self.find_id(self.components[env_lc].menus['Env Load Case - Wind Choice|||'][-1]['Wind'])
				
			env_lc_data.append([env_lc, current, wave, wind])
		return env_lc_data	
		
	def assemble_analysis_component_data(self):
		analysis_data = []
		analysis_components = self.get_all_components('Analysis')
		
		for analysis in analysis_components:
			riser = 'None'
			
			if 'Analysis - Drilling Riser Name|||' in self.components[analysis].menus.keys():
				riser = self.find_id(self.components[analysis].menus['Analysis - Drilling Riser Name|||'][-1]['Riser Name'])
				
			analysis_data.append([analysis, riser])

	def assemble_fluid_tension_data(self):
		fluid_tension_data = []
		analysis_components = self.get_all_components('DriftOff-Weak Point Analysis')

		for analysis in analysis_components:
			analysis_type = 'Drift-off'
			
			if 'Drift-Off/Weak Point Analysis - Load Cases |||' in self.components[analysis].menus.keys():
				for row in self.components[analysis].menus['Drift-Off/Weak Point Analysis - Load Cases |||']:
					case = 'None'
					fluid = 'None'
					tension = 'None'
					
					if 'Load Case' in row.keys():
						case = row['Load Case']
					if 'Top Tension' in row.keys():
						tension = row['Top Tension']
					if 'Internal Fluid' in row.keys():
						fluid = self.find_id(row['Internal Fluid'])
					
					fluid_tension_data.append(['Drift-Off', analysis, case, fluid, tension])
					
		return fluid_tension_data
		
	def assemble_drift_off_limits(self):
		'''
		Generates a pandas dataframe of the drift-off limits for all load cases.
		The columns of the dataframe represent the load case names
		The index of the dataframe is the various components shown in the index list below
		'''
		
		index = ['Telescopic Joint Stroke', 'Tensioner Stroke', 'UFJ Angle', 'LFJ Angle', 'Connector Bending Moment',
					'Wellhead Bending Moment', 'Conductor Bending Stress', 'Conductor Bending Moment', 'Riser Von Mises Stress',
					'Conductor Von Mises Stress', 'Smallest Allowable Alert Offset', 'Maximum Allowable POD Offset', 'Maximum Allowable Alert Offset',
					'Heave', 'Tide', 'Safety Margin', 'Run Analysis for Duration', 'Use Weak Point Limits']

		df_limit_data = pd.DataFrame(index=index, columns=[analysis for analysis in self.get_all_components('DriftOff-Weak Point Analysis')])
		
		for analysis in self.get_all_components('DriftOff-Weak Point Analysis'):
			if 'Drift-Off/Weak Point Analysis - Limits |||' in self.components[analysis].menus.keys():
				for param in self.components[analysis].menus['Drift-Off/Weak Point Analysis - Limits |||'][-1].keys():
					try:
						limit = float(self.components[analysis].menus['Drift-Off/Weak Point Analysis - Limits |||'][-1][param])
					except:
						limit = np.nan
					df_limit_data.at[param, analysis] = limit
					
		
		return df_limit_data

	def assemble_drift_off_data(self):
		df_drift_off = pd.DataFrame(index=["EDS"], columns=[analysis for analysis in self.get_all_components('DriftOff-Weak Point Analysis')])
		
		for analysis in self.get_all_components('DriftOff-Weak Point Analysis'):
			eds = {}

			#Get Defined EDS
			if 'Drift-Off/Weak Point Analysis - Timings|||' in self.components[analysis].menus.keys():
				for idx, row in enumerate(self.components[analysis].menus['Drift-Off/Weak Point Analysis - Timings|||']):
					if row['EDS Timing Sequence'] == '':
						eds_name = f'EDS {idx+1}'
					else:
						eds_name = row['EDS Timing Sequence']
				eds[eds_name] = {'Red Alert to POD': row['Red Alert to POD Time']}
			
			#Get EDS for each load case
			if 'Drift-Off/Weak Point Analysis - Load Cases |||' in self.components[analysis].menus.keys():
				for idx, row in enumerate(self.components[analysis].menus['Drift-Off/Weak Point Analysis - Load Cases |||']):
					if row['EDS Timing Sequences'] in eds.keys():
						df_drift_off.at["EDS", analysis] = eds[row['EDS Timing Sequences']]['Red Alert to POD']
		
		return df_drift_off

	def assemble_recoil_data(self):
		analysis_components = self.get_all_components("Recoil Analysis")
		recoil_data = [["Analysis"], ["Load Case"], ['Top Tension'], ["Internal Fluid"]]
		
		for analysis in analysis_components:
			
			if "Recoil Analysis - Load Cases - Define |||" in self.components[analysis].menus.keys():
				for idx, row in enumerate(self.components[analysis].menus["Recoil Analysis - Load Cases - Define |||"]):
					load_case = row["Load Case"]
					top_tension = row["Top Tension"]
					fluid = row["Internal Fluid"]
					
					recoil_data[0].append(analysis)
					recoil_data[1].append(load_case)
					recoil_data[2].append(top_tension)
					recoil_data[3].append(fluid)
		
		for p_idx, param in enumerate(recoil_data):
			for row_idx, row in enumerate(param):
				if row == "":
					recoil_data[p_idx][row_idx] = None
					
					
		return recoil_data
		
	def get_riser_weight(self, riser):
		stackup = self.get_riser_stackup(riser)
		found_tj = False
		
		riser_weight = 0
		for joint in stackup:
			if joint[2] not in ['BOP', 'LMRP']:
				if joint[2] == 'Telescopic Joint':
					found_tj = True
				if found_tj:
					riser_weight += joint[1]
		
		return riser_weight, stackup
		
	def get_riser_stackup(self, riser):
		stackup = []
		for row in self.components[riser].menus['DR Storage Menu|||']:
			joint = self.find_id(row['Joint'])
			print(joint)
			number_of_joints = int(row['Number of Joints'])
			top_elv = float(row['Top Elevation'])
			btm_elv = float(row['Bottom Elevation'])
			
			submerged = True
			weight = 0
			
			if self.components[joint].component_type != 'Conductor-Casing':

				if self.components[joint].component_type == 'Drilling Riser Joint':
					weight_menus = ['Drilling Riser Joint - Properties|||', 'Drilling Riser Joint - Buoyancy Foam|||']
					weight_keys = ['Weight in Water - W(water)', 'Total Weight in Water']
				elif self.components[joint].component_type == 'Rotating Control Device':
					weight_menus = ['RCD - Above Seal Properties|||', 'RCD - Seal Properties|||', 'RCD - Below Seal Properties|||']
					weight_keys = ['Weight in Water - W(water)', 'Weight in Water - W(water)', 'Weight in Water - W(water)']
				elif self.components[joint].component_type == 'Flex Joint':
					weight_menus = ['Linear Properties - Define|||']
					weight_keys = ['Weight in Water']
				elif self.components[joint].component_type == 'LMRP':
					weight_menus = ['Properties  -  Define|||']
					weight_keys = ['Weight in Water']
				elif self.components[joint].component_type == 'BOP':
					weight_menus = ['Properties - Define |||']
					weight_keys = ['Weight in Water']
				elif self.components[joint].component_type == 'Telescopic Joint':
					weight_menus = ['Outer Barrel Properties  -  Define|||', 'Inner Barrel Properties - Define|||']
					weight_keys = ['Weight in Water', 'Weight in Water']
				elif self.components[joint].component_type == 'Wellhead Connector':
					weight_menus = ['Wellhead - High Pressure Wellhead Housing Stickup|||', 'Wellhead - HPWHH and LPWHH|||']
					weight_keys = ['Weight in Water', 'Weight in Water']

				if submerged:
					
					for idx, menu in enumerate(weight_menus):
						if menu in self.components[joint].menus.keys():
							if self.components[joint].menus[menu][0][weight_keys[idx]] != '':
								weight += self.components[joint].menus[menu][0][weight_keys[idx]]
					
			for i in range(number_of_joints):
				stackup.append([joint, weight, self.components[joint].component_type, top_elv, btm_elv])

		return stackup

	def get_riser_aux_line_data(self, riser, convert_to_feet=True):
		aux_line_data = []
		
		for idx, row in enumerate(self.components[riser].menus['Auxiliary Line Properties  |||']):
			name = row['Auxiliary Line']
			if name.strip() == '':
				name = self.default_lines[idx]
			id = row['Internal Diameter, Di']
			if convert_to_feet:
				id = round(id/12, 3)
			
			aux_line_data.append({'Name': name, 'ID': id})
			
		print(aux_line_data)

		return aux_line_data
		
	def get_soil_profile(self, soil):
		#soils = self.get_all_components('Soil Structure')
	
		# Get the soil structure list
		soil_list = {}
		if 'Soil Structure List|||' in self.components[soil].menus.keys():
			for row in self.components[soil].menus['Soil Structure List|||']:
				print(row['Name'])
				soil_list[row['GUID']] = row['Name']

		
		# Get data from each profile in soil structure list
		profile = []
		
		for menu in self.components[soil].menus.keys():
			if menu != "Soil Structure List|||":
				soil_type = None
				if 'Stiff' in menu:
					soil_type = 'Stiff Clay'
				elif 'Sand' in menu:
					soil_type = 'Sand'
				elif 'Soft' in menu:
					soil_type = 'Soft Clay'
				
				params = {'Undrained Shear Strength': None, 'Submerged Unit Weight': None, 'Ultimate Resistance Coefficient': None,
							'Static Loading Constant': None, 'Strain at Half Max Stress': None, 'Scour Depth': None,
							'Empirical Constant, J': None, 'Angle of Internal Friction': None, 'C1': None,
							'C2': None, 'C3': None, 'k': None}
				
				for row in self.components[soil].menus[menu]:
					if '- Parameters By Dept' in menu and 'GUID' in row.keys():
						
						for param in params.keys():
							if param in row.keys():
								params[param] = row[param]

						profile.append([soil_list[row['GUID']], soil_type, row['Depth']])
						for param in params.keys():
							profile[-1].append(params[param])
		
		columns = ['Name','Soil Type', 'Depth']
		for param in params.keys():
			columns.append(param)
			
		soil_profile_df = pd.DataFrame(profile, columns=columns)		
		soil_profile_df["isSoilChanged"] = soil_profile_df["Soil Type"].shift(1, fill_value=soil_profile_df["Soil Type"].head(1)) != soil_profile_df["Soil Type"]		
		print(profile)
		return soil_profile_df
		
	def get_vessel_reference_point(self):
		vessel_reference_points = {}
		vessels = self.get_all_components('Standard Vessel')
		for vessel in vessels:
			vessel_reference_points[vessel] = {}
			for param in self.components[vessel].menus['Reference Point Location|||'][0]:
				vessel_reference_points[vessel][param] = convert_to_number(self.components[vessel].menus['Reference Point Location|||'][0][param])
		
		return vessel_reference_points
		
class DPXComponent:
	def __init__(self, name, component_id, component_type, dpx):		
		self.name = name
		self.component_id = component_id
		self.component_type = component_type
		self.dpx = dpx
		
		self.menus = {}
		self.options = {}
		
	def assemble_current_plot_data(self):
		current_data = {'velocities': [], 'depths': []}
		
		if self.component_type == 'Current':
			for row in self.menus['Current - Piecewise Linear - Knots|||']:
				current_data['velocities'].append(row['Velocity'][0])
				current_data['depths'].append(row['Distance Below Mean Waterline'][0])
		else:
			print('*** Not a Current')
			
		return current_data
		
	def assemble_conductor_casing_data(self):
		conductor_casing_stack = []
		params = {'Type': self.options['Conductor Casing Installation Options|||']}
		
		if self.component_type == 'Drilling Riser':
			for row in self.menus['DR Storage Menu|||']:
				joint = self.dpx.components[self.dpx.find_id(row['Joint'][0])]
				if joint.component_type == 'Conductor-Casing':
					conductor_casing_stack.append({})
					conductor_casing_stack[-1]['Conductor OD'] = joint.menus['Properties Detailed - Define|||'][0]['External Diameter, Do'][0]
					conductor_casing_stack[-1]['Conductor ID'] = joint.menus['Properties Detailed - Define|||'][0]['Internal Diameter, Di'][0]
					conductor_casing_stack[-1]['Casing OD'] = joint.menus['Surface Casing - Define|||'][0]['External Diameter, Do'][0]
					conductor_casing_stack[-1]['Casing ID'] = joint.menus['Surface Casing - Define|||'][0]['Inner Diameter, Di'][0]
					conductor_casing_stack[-1]['Top Elv'] = row['Top Elevation'][0]
					conductor_casing_stack[-1]['Btm Elv'] = row['Bottom Elevation'][0]
		
		return conductor_casing_stack, params

if __name__ == '__main__':	
	#dpx = DPX(r'C:\Users\domhnall.morrisey\Documents\Analysis\OP195659 Chevron Egpyt\OP195659 Chevron - Stena Forth Egypt.dpx')
	dpx = DPX(r'\\r-ana-iegwmcs-5\e\114-Projects\OP211828 Tullow Oil - Dropped Riser and Transit Assessment\01 VIV Transit Fatigue\OP211828 Tullow Oil - V-Rig Ghana VIV Transit Rev1.dpx')
	
	stackup = dpx.get_riser_stackup("8.56ppg Riser 1500m WD Transit")
	for j in stackup:
		print(j[0])
