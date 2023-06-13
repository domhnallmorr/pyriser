import math
import pandas as pd
import seaborn as sns
import os

class DasFile():
	"""
	Author:
	-------------
		- Domhnall Morrisey 19/05/2021
		
	Prerequisites:
	-------------
		- Python > 3.9
		- pandas

	Limitations: 
	-------------
		- Not good handling of metric units at the moment
		- Limited error handling at the moment

	Key Variables: 
	-------------
		- self.models: nested dictionary containing each $model, key is model number 0, 1, 2, etc. Value is an dictionary containing each * section in the model e.g. {1: {'NODE': []}, 2: {'NODE': []}} Note it is NOT 0 indexed!! Might change that in future.
		- self.load_case_summary: nested dictionary containing each $LOAD CASE
		
	TO DO: 
	-------------
		- Improve get_drag_daf method
	"""
	def __init__(self, das_file, verbose=False, print_name=True):
	
		'''
		:param das_file: (``string``) - full path of das file to be read
		:param verbose (``boolean`` - optional): - Print internal messages if True (default value False).  
		:param print_name (``boolean`` - optional): - Print file name if True (default value True). Useful for tracking progress if reading multiple files
		'''	
		self.print_name = print_name
		if print_name:
			print(das_file)

		#Setup instance variables
		self.das_file = das_file
		self.verbose = verbose
		self.setup_variables()
		
		#read the das file data into memory
		self.read_das_file()
		self.parse_das_file_data()
		
		self.get_units()
		self.get_analysis_type()
		self.water_depth = self.process_water_depth()
		self.get_star_database()
		
		if self.verbose:
			print(f"Water depth processed as {self.water_depth}{self.length_unit}")
		self.process_soil()
		self.sum_all_soil_values()
		self.gen_load_case_summary()
		self.process_hydro_sets()
		self.handle_errors() #print errors after reading file
		
	def setup_variables(self):
		'''
			This function setups default placeholder variables
		'''
		self.file_name = os.path.basename(self.das_file)
		self.load_case_summary = None
		self.water_depth = None
		self.daf = None
		self.wh_stickup = None
		self.pip_data = None
		self.das_data = {'headers': {'headers': []}}
		self.models = {}
		self.no_models = 0
		self.load_cases = {}
		self.no_load_cases = 0
		self.rao_equivalent_waves = []
		self.load_case_summary = {}
		self.p_y_curves = {}
		self.soil_sum = 0
		self.units = None
		self.analysis_type = None
		self.database_start = None
		self.daf = None #drag amplification factor, run get_drag_daf method to (attempt) to estimate this value
		
		self.length_unit = None #this is set to ft or m in the get_units method
		
		self.units_dict = {'imperial': {'length': 'ft'},
							'metric': {'length': 'm'}}
		
		self.output_files = []
		self.errors = [] #list for capturing any error messages
		
	def read_das_file(self):
		
		'''
			This function reads the das file into a list (self.data)
			Commented lines are ignored, leading space and newline char are removed
		'''
		self.data = []
		
		with open(self.das_file) as f:
			while True:
				line = f.readline()
				
				if not line:
					break # break at end of file
					
				line = line.rstrip()
				if len(line) > 0:
					if line[0].lower() != 'c': #ignore commented lines
						self.data.append(line.strip().rstrip()) #remove leading space and new lines


	def parse_das_file_data(self):
	
		'''
			Parse the self.data list
			$model sections are added to self.models dict
			$Load Case sections are added to self.load_cases dict
			All other dollar sections are added to self.das_data dict
		'''
		
		dollar_section = 'headers'	#default dollar ($) section
		star_section = 'headers' #default star (*) section
		
		for line in self.data:
			#Handle for Dollar Section Change
			if line[0] == '$':
				dollar_section = line
				
				if dollar_section == '$MODEL':
					self.no_models += 1
					self.models[self.no_models] = {}
				
				if dollar_section == '$LOAD CASE':
					self.no_load_cases += 1
					self.load_cases[self.no_load_cases] = {}	
				else:
					self.das_data[dollar_section] = {}			

			#Handle for Star Section Change		
			elif line[0] == '*':
				star_section = line
				if dollar_section == '$MODEL':
					self.models[self.no_models][star_section] = []
				elif dollar_section == '$LOAD CASE':
					self.load_cases[self.no_load_cases][star_section] = []
				else:
					self.das_data[dollar_section][star_section] = []

			else:
				if dollar_section == '$MODEL':
					self.models[self.no_models][star_section].append(line)
				elif dollar_section == '$LOAD CASE':
					self.load_cases[self.no_load_cases][star_section].append(line)				
				else:
					self.das_data[dollar_section][star_section].append(line)
					
		if self.verbose:
			print(f"{self.no_models} Model(s) Found")
			print(f"{self.no_load_cases} Load Case(s) Found")

	def process_water_depth(self, model=1):
		'''
			get the water depth from *OCEAN
			This defaults to model 1 (normally don;t have different WDs in the das file models)
			
			:return water_depth (``float``) - float value of the water_depth
		'''
		
		water_depth = None
		if '*OCEAN' in self.models[model].keys():
			water_depth = float(self.models[model]['*OCEAN'][0].split(',')[0])
		
		return water_depth

	def get_units(self):
		'''
			Find the units
			Also defines units such as feet/meters
		'''
		if '$ANALYSIS' in self.das_data.keys():
			if '*UNITS' in self.das_data['$ANALYSIS'].keys():
				for d in self.das_data['$ANALYSIS']['*UNITS']:
					if 'UNITS=' in d:
						self.units = d.split('=')[1].strip()
		
		if self.units: #handle for units still being None for whatever reason
			self.length_unit = self.units_dict[self.units.lower()]['length']
		else:
			self.errors.append('Units not found')

		if self.verbose:
			print(f'Units Identified as {self.units}')

	def get_analysis_type(self):
		'''
			Get the analysis type from *ANALYSIS TYPE
		'''
		if '*ANALYSIS TYPE' in self.das_data['$ANALYSIS'].keys():
			for d in self.das_data['$ANALYSIS']['*ANALYSIS TYPE']:
				if 'TYPE=' in d:
					self.analysis_type = d.split('=')[1].strip()

		if self.verbose:
			print(f'Analysis Type Identified as {self.analysis_type}')

	def gen_load_case_summary(self):
	
		'''
			Long function to parse each $LOAD CASE section
		'''
		for l in self.load_cases.keys():
			self.load_case_summary[l] = {}
			
			# ### LOAD CASE NAME ###############
			name = None #default value
			
			for d in self.load_cases[l]['*DIRECTORY']:
				if 'DIRECTORY=' in d:
					name = d.split('DIRECTORY=')[1].strip()
					name = name.replace('"', '')
			
			self.load_case_summary[l]["Name"] = name
			self.load_case_summary[l]["Database Start"] = self.database_start
			
			# ### SOIL #########################
			self.load_case_summary[l]["Soil Sum"] = self.soil_sum
			
			# ### TIME #########################
			time_type = None
			ramp = None
			duration = None
			if "*TIME" in self.load_cases[l].keys():
				# FIRST DETERMINE WHETER FIXED OR VARIABLES

				for index, d in enumerate(self.load_cases[l]['*TIME']):
					if 'STEP=FIXED' in d:
						time_type = 'FIXED'
						break				
				
				if time_type == 'FIXED':
					ramp = round(float(self.load_cases[l]['*TIME'][index+1].split(',')[3]),3)
					start = round(float(self.load_cases[l]['*TIME'][index+1].split(',')[0]),3)
					end = round(float(self.load_cases[l]['*TIME'][index+1].split(',')[1]),3)
					duration = round(end-start,3)
					
			self.load_case_summary[l]['Time Type'] = time_type
			self.load_case_summary[l]['Ramp'] = ramp
			self.load_case_summary[l]['Duration'] = duration

			
			# ### INTERNAL FLUID ###############
			fluid_level = 0.0
			internal_fluid = 0.0
			pressure = 0.0
			axial_inertia = None
			fluid_count = 0
			
			for index, d in enumerate(self.load_cases[l]['*INTERNAL FLUID']):
				if 'SET=_InternalFluid' in d and index < len(self.load_cases[l]['*INTERNAL FLUID'])-1:
					
					fluid_data = (self.load_cases[l]['*INTERNAL FLUID'][index+1]).split(',')
					
					fluid_level = float(fluid_data[0]) #level AML
					internal_fluid = float(fluid_data[1])
					pressure = float(fluid_data[2])
					
					if self.units.lower() == 'imperial':
						pressure = pressure/144 # lb/ft2 to psi
						
					if len(fluid_data) >= 5:
						axial_inertia = int(fluid_data[5])
					
					if self.units == 'IMPERIAL':
						internal_fluid = round(internal_fluid*4.3,2) #slugs/ft3 to ppg
					self.load_case_summary[l][f'Internal Fluid Level {fluid_count}'] = fluid_level
					self.load_case_summary[l][f'Internal Fluid {fluid_count}'] = internal_fluid
					self.load_case_summary[l][f'Fluid Pressure {fluid_count}'] = pressure
					self.load_case_summary[l][f'Axial Inertia {fluid_count}'] = axial_inertia
					fluid_count += 1
			self.load_case_summary[l]['Internal Fluid Count'] = fluid_count
			
			# ### TOP TENSION ###############
			top_tension = 0.0
			if '*TOP TENSION' in self.load_cases[l].keys():
				for index, d in enumerate(self.load_cases[l]['*TOP TENSION']):
					if 'SET=_Tensioner' in d and index < len(self.load_cases[l]['*TOP TENSION'])-1:
						
						top_tension = round(float(self.load_cases[l]['*TOP TENSION'][index+1])/1000,1)
			self.load_case_summary[l]['Top Tension'] = top_tension

			
			# ### WAVE #####################
			wave_type = None
			hs = None
			tp = None
			wave_dir = None
			
			wave_amp = None #for regular wave
			wave_period = None #for regular wave
			
			if '*WAVE' in self.load_cases[l].keys():
				# FIRST IDENTIFY WHAT KIND OF WAVE IS USED
				for index, d in enumerate(self.load_cases[l]['*WAVE']):
					if 'TYPE=JONSWAP, FREQUENCY=AREA, SPEC=HSTPGAMMA' in d:
						wave_type = "Jonswap HSTPGAMMA"
						break
					elif 'TYPE=JONSWAP, FREQUENCY=AREA, SPEC=HSTP' in d:
						wave_type = 'Jonswap HSTP'
						break
					elif 'TYPE=REGULAR' in d:
						wave_type = 'Regular'
						break
				
				# JONSWAP HSTP
				if wave_type == 'Jonswap HSTPGAMMA':
					if index < len(self.load_cases[l]['*WAVE']) -1 :
						wave_data = (self.load_cases[l]['*WAVE'][index+1]).split(',')
						hs = round(float(wave_data[0]),3)
						tp = round(float(wave_data[1]),3)
						wave_dir = round(float(wave_data[7]),3)

				if wave_type == 'Jonswap HSTP':
					if index < len(self.load_cases[l]['*WAVE']) -1 :
						wave_data = (self.load_cases[l]['*WAVE'][index+1]).split(',')
						hs = round(float(wave_data[0]),3)
						tp = round(float(wave_data[1]),3)
						wave_dir = round(float(wave_data[6]),3)
				
				# REGULAR WAVE
				if wave_type == 'Regular':
					if index < len(self.load_cases[l]['*WAVE']) -1 :
						wave_data = (self.load_cases[l]['*WAVE'][index+1]).split(',')
						wave_amp = round(float(wave_data[0]),3)
						wave_period = round(float(wave_data[1]),3)
						wave_dir = round(float(wave_data[2]),3)
						
			self.load_case_summary[l]['Wave Type'] = wave_type
			self.load_case_summary[l]['Wave Dir'] = wave_dir
			self.load_case_summary[l]['Hs'] = hs
			self.load_case_summary[l]['Tp'] = tp
			self.load_case_summary[l]['Wave Amplitude'] = wave_amp
			self.load_case_summary[l]['Wave Period'] = wave_period
			

			# ### WIND #####################
			wind_speed = None
			wind_dir = None
			
			if '*WIND' in self.load_cases[l].keys():
				wind_speed = round(float(self.load_cases[l]['*WIND'][0].split(',')[0]),3)
				wind_dir = round(float(self.load_cases[l]['*WIND'][0].split(',')[1]),3)

			self.load_case_summary[l]['Wind Speed'] = wind_speed
			self.load_case_summary[l]['Wind Dir'] = wind_dir	

			# ### CURRENT #####################	
			current_type = None
			current_specification = None
			avg_current = 0
			surface_current = 0
			surface_current_dir = None
			current_profile = []
			
			if '*CURRENT' in self.load_cases[l].keys():
				# FIRST IDENTIFY WHAT KIND OF CURRENT IS USED
				for index, d in enumerate(self.load_cases[l]['*CURRENT']):
					if 'TYPE=PIECEWISE LINEAR' in d:
						current_type = 'PIECEWISE LINEAR'
						comma_count = 2 # for getting profile
						if 'DESCENDING' in d:
							current_specification = 'DESCENDING'
						else:
							current_specification = 'ASCENDING'
						break
				
				# GET PROFILE
				
				for i, d in enumerate(self.load_cases[l]['*CURRENT']):
					if i > index and d.count(',') == comma_count:
						d = d.split(',')
						current_profile.append(tuple(d))
						avg_current += float(d[1])
						
						if current_specification == 'DESCENDING' and len(current_profile) == 1:#first point in profile
							surface_current = float(d[1])
							surface_current_dir = float(d[2])
						
				if current_specification == 'ASCENDING':
					surface_current = float(current_profile[-1][1])
					surface_current_dir = float(current_profile[-1][2])
						
				avg_current = avg_current/len(current_profile)
				
			self.load_case_summary[l]['Current Type'] = current_type				
			self.load_case_summary[l]['Current Spec'] = current_specification				
			self.load_case_summary[l]['Current Profile'] = tuple(current_profile)
			self.load_case_summary[l]['Average Current'] = avg_current
			self.load_case_summary[l]['Surface Current'] = surface_current
			self.load_case_summary[l]['Surface Current Direction'] = surface_current_dir

			# ### DRIFT PARAMETERS ########
			self.eds = None
			self.telescopic_joint_limit = None
			self.tensioner_limit = None
			self.ufj_limit = None
			self.lfj_limit = None
			self.wh_bm_limit = None
			self.riser_vms_limit = None
			self.cond_vms_limit = None
			
			if '*DRIFT-OFF LIMITS' in self.load_cases[l].keys():
				for index, d in enumerate(self.load_cases[l]['*DRIFT-OFF LIMITS']):
					if 'MAX SLJ STROKE' in d:
						self.telescopic_joint_limit = float(d.split('=')[-1])
					if 'MAX TEN STROKE' in d:
						self.tensioner_limit = float(d.split('=')[-1])
					if 'MAX UFJ ANGLE' in d:
						self.ufj_limit = float(d.split('=')[-1])
					if 'MAX LFJ ANGLE' in d:
						self.lfj_limit = float(d.split('=')[-1])
					if 'MAX WH BENDING' in d:
						self.wh_bm_limit = float(d.split('=')[-1])
					if 'MAX VM STRESS' in d:
						self.riser_vms_limit = float(d.split('=')[-1])							
					if 'MAX CON VM STRESS' in d:
						self.cond_vms_limit = float(d.split('=')[-1])	
					if 'RED TO POD TIME' in d:
						self.eds = float(d.split('=')[-1])
			
			self.load_case_summary[l]['EDS'] = self.eds
			self.load_case_summary[l]['TJ Limit'] = self.telescopic_joint_limit
			self.load_case_summary[l]['Ten Limit'] = self.tensioner_limit
			self.load_case_summary[l]['UFJ Limit'] = self.ufj_limit
			self.load_case_summary[l]['LFJ Limit'] = self.lfj_limit
			self.load_case_summary[l]['WH BM Limit'] = self.wh_bm_limit
			self.load_case_summary[l]['Riser VMS Limit'] = self.riser_vms_limit
			self.load_case_summary[l]['Cond VMS Limit'] = self.cond_vms_limit
			
			
			# ### RAO #####################
			
			rao_type = None
			rao = None
			
			if '*RAO' in self.load_cases[l]:

				for index, d in enumerate(self.load_cases[l]['*RAO']):
					if 'Equivalent Wave Amp' in d:
						try:
							d = d.replace('\t', '').split(',')
							amp = d[0].split()[-1]
							period = d[1].split()[-1]
							rao_type = 'Equivalent Wave'
							rao = [amp, period]
						except:
							print(f'*** Found Equiv Wave (see below) but could not parse amplitude and period\n{line}')				
					if 'FIRSTRAO=YES' in d and len(list(self.load_case_summary.keys())) > 0:
						first_case =  list(self.load_case_summary.keys())[0]
						
						if self.load_case_summary[first_case]['RAO'] and self.load_case_summary[first_case]['RAO Type']:
							rao = self.load_case_summary[first_case]['RAO']
							rao_type = self.load_case_summary[first_case]['RAO Type']
			
			self.load_case_summary[l]['RAO'] = rao
			self.load_case_summary[l]['RAO Type'] = rao_type
			
			
			# ### DISCONNECT TIME  AND BULK MODULUS (RECOIL) #####################
			disconnect_time = None
			phase = None
			periods_before_disconnect = None
			bulk_modulus = None
			fanning_friction = None
			discharge_coeff_out = None
			discharge_coeff_in = None
			atmospheric_pressure = None
			
			if '*TIME,DISCONNECT' in self.load_cases[l]:
				for index, d in enumerate(self.load_cases[l]['*TIME,DISCONNECT']):
					d = d.split(',')
					disconnect_time = float(d[0])
				
				#calculate phase
				if disconnect_time and self.load_case_summary[l]['Wave Period']:
					if disconnect_time > self.load_case_summary[l]['Wave Period']:
						
						periods_before_disconnect = disconnect_time // self.load_case_summary[l]['Wave Period']
						r = disconnect_time % self.load_case_summary[l]['Wave Period'] #get remaineder
						
						phase = round((r/self.load_case_summary[l]['Wave Period'])*360,1)

				#bulk modulus
				if '*DRILLING MUD' in self.load_cases[l]:
					for index, d in enumerate(self.load_cases[l]['*DRILLING MUD']):
						if 'SET' not in d:
							d =d.split(',')
							bulk_modulus = float(d[1])
							fanning_friction = float(d[2])
							discharge_coeff_out = float(d[3])
							discharge_coeff_in = float(d[4])
							atmospheric_pressure = float(d[6])
			
			self.load_case_summary[l]['DISCONNECT TIME'] = disconnect_time	
			self.load_case_summary[l]['PHASE'] = phase	
			self.load_case_summary[l]['PERIODS B4 Disconnect'] = periods_before_disconnect	
			self.load_case_summary[l]['BULK MODULUS'] = bulk_modulus	
			self.load_case_summary[l]['Fanning Friction'] = fanning_friction
			self.load_case_summary[l]['Discharge Coeff. Out.'] = discharge_coeff_out
			self.load_case_summary[l]['Discharge Coeff. In.'] = discharge_coeff_in
			self.load_case_summary[l]['Atmospheric Pressure'] = atmospheric_pressure
			
			# ### Offset #####################		
			offset = None
			offset_y = None
			offset_z = None
			offset_option = 'dist'
				
			if '*OFFSET' in self.load_cases[l]:
				for index, d in enumerate(self.load_cases[l]['*OFFSET']):
					if 'OPTION' in d:
						offset_option = d.split('=')[-1]
				offsets = self.load_cases[l]['*OFFSET'][-1].split(',')
				offset = round(math.sqrt(float(offsets[1])**2 + float(offsets[2])**2),2)
				offset_y = float(offsets[1])
				offset_z = float(offsets[2])
				
				if offset_y < 0 and offset_z < 0:
					offset = offset*-1
	
			self.load_case_summary[l]['Offset'] = offset
			self.load_case_summary[l]['Offset Y'] = offset_y
			self.load_case_summary[l]['Offset Z'] = offset_z
			self.load_case_summary[l]['Offset Option'] = offset_option

			# ### DAMPING #####################
			damping = ''
			set = ''
			damping_coeff = ''
			if '*DAMPING' in self.load_cases[l]:
				for index, d in enumerate(self.load_cases[l]['*DAMPING']):
					if 'set=' in d.lower():
						set = d.split('=')[1].strip()
					elif len(d.split(',')) == 3:
						damping_coeff = d.split(',')[0].strip()
						damping = damping + set + ' (' + damping_coeff + '), '
			if damping == '':
				damping = 'No Damping'
			self.load_case_summary[l]['Damping'] = damping
			
			
		#create a pandas DF from the self.load_case_summary dict
		self.df_lc_summary = pd.DataFrame.from_dict(self.load_case_summary, orient='index')
		self.df_lc_summary['Path'] = self.das_file

	def write_load_case_summary(self, output_file):
		'''
			write the self.df_lc_summary DF to excel
			:param output_file: (``string``) - full path of excel file to be written (must end in .xlsx) 
		'''
		
		if output_file.endswith('.xlsx'):
			if len(list(self.load_case_summary.keys())) > 0:
				first_case = list(self.load_case_summary.keys())[0]
				
				columns = list(self.load_case_summary[first_case].keys())
				
				# df = pd.DataFrame.from_dict({(i,j): self.load_case_summary[i][j] 
						   # for i in self.load_case_summary.keys() 
						   # for j in self.load_case_summary[i].keys()},
					   # orient='index')
				self.df_lc_summary = pd.DataFrame.from_dict(self.load_case_summary, orient='index')
				self.df_lc_summary['Path'] = self.das_file
				self.df_lc_summary.to_excel(output_file)
		else:
			raise Exception("Load case summary Excel output file name must end with .xlsx")

	def process_hydro_sets(self):
		'''
			This method processes the hydrodyanmic set for each $MODEL into a pandas DataFrame
			The method creates an instance variable called self.df_hydro_sets which is the DataFrame created.
			Index of the DF is the set names. Note for Reynolds hydro sets, the set name has "Re - Reynolds Number" added for each Reynolds number found for that set.
			The columns of the DF are the individual hydro parameters (Normal Drag, Tangential Drag, etc). See coeffs variable.
		'''
		hydro_sets = {}
		self.df_hydro_sets = None
		option = None
		diameter = None
		hydro_type = None
		
		for model in self.models.keys():
			if '*HYDRODYNAMIC SETS' in self.models[model]:
				for s in self.models[model]['*HYDRODYNAMIC SETS']:
					if 'SET=' in s:
						s = s.replace('SET=', '')
						set_name = s.split(',')[0].strip()
						if ',' in s:
							hydro_type = s.split(',')[1].strip().replace('TYPE=', '').lower()							
						
						if hydro_type.lower() == 'constant':
							hydro_sets[set_name] = {'Type': hydro_type, 'Diameter': diameter, 'Option': option,
												'Normal Drag': None, 'Tangential Drag': None,
												'Normal Inertia': None, 'Normal Added Mass': None, 'Tangential Added Mass': None,
												'Drag Lift': None}

					elif 'DIAMETER=' in s:
						diameter = s.split('DIAMETER=')[1].strip()
					elif 'OPTION=' in s:
						option = s.split('OPTION=')[1].strip()
					else: # handle coefficients
						coeffs = ['Normal Drag', 'Tangential Drag','Normal Inertia', 'Normal Added Mass', 'Tangential Added Mass',
												'Drag Lift']
						if hydro_type == 'constant':					
							for idx, c in enumerate(s.split(',')):
								hydro_sets[set_name][coeffs[idx]] = float(c)
						else:
							reynolds = float(s.split(',')[0])
							hydro_sets[f'{set_name} Re - {reynolds}'] = {'Type': hydro_type, 'Diameter': diameter, 'Option': option,
												'Normal Drag': None, 'Tangential Drag': None,
												'Normal Inertia': None, 'Normal Added Mass': None, 'Tangential Added Mass': None,
												'Drag Lift': None}
							for idx, c in enumerate(s.split(',')[1:]):#ignore reynnolds number
								hydro_sets[f'{set_name} Re - {reynolds}'][coeffs[idx]] = float(c)												
			
			if self.df_hydro_sets is None:
				self.df_hydro_sets = pd.DataFrame.from_dict(hydro_sets, orient='index') #initialise the DataFrame
			else:
				self.df_hydro_sets = pd.concat([self.df_hydro_sets, pd.DataFrame.from_dict(hydro_sets, orient='index')])
		
		
	def get_drag_daf(self):
		'''
			This method is a fairly crude attempt to estimtae DAF appllied to drag ceofficients
			Method attempts to find a pup or a slick joint in the hydro sets
			DAF is defined as 1 if a slick or a pup joint is found with CdN of 1.2
		'''

		if '*HYDRODYNAMIC SETS' in self.models[1].keys():
			for idx, d in enumerate(self.models[1]['*HYDRODYNAMIC SETS']):
				if 'SET=' in d:
					if 'Slick Joint' in d or 'Pup' in d:
						if 'reynolds' not in d.lower():
							try:
								#normal drag/1.2 = DAF
								self.daf = round(float(self.models[1]['*HYDRODYNAMIC SETS'][idx+1].split(',')[0])/1.2, 3) #note 1.2 drag coeff is hard coded
								break
							except Exception as e:
								print(f'Failed to Calculate DAF for set {d}')
		
		if self.verbose:
			if self.daf:
				print(f'Drag Amplification Factor (DAF) estimated as {self.daf}')
			else:
				print('Drag Amplificaition Factor (DAF) could not be estimated, ensure *HYDRODYNAMIC SETS contains a joint with "Pup" or "Slick Joint" in the set name.')
			
			print("Note Normal Drag / 1.2 = DAF")

	def get_wellhead_stickup(self):
		'''
			attempt to determine wellhead stickup by findining element set with LPWHH and HPWHH
		'''
		
		self.wh_stickup = None
		self.wh_stickup_elm = None
		element_sets = self.process_element_sets(self.models[1])

		for set in element_sets:
			
			if 'lpwh' in set.lower() and 'hpwh' in set.lower():
				
				start_elm = int(element_sets[set][0])
				end_elm = int(element_sets[set][-1])
				
				self.wh_stickup_elm = min((start_elm, end_elm))
				
				break

	def process_element_sets(self, model=1):
		
		'''
			Process the element sets for a given model
			
			:param model: (``int``) - model number to be processed, defaults to 1	
			:return elements (``dict``) - each key is the set name, value is a list of elements in that set
		'''
		element_sets = {}
		if '*ELEMENT SETS' in self.models[model].keys():
			element_set_data = self.models[model]['*ELEMENT SETS']
			set = ''
			for e in element_set_data:

				if e[0:4] == 'SET=':
					set = e[4:].strip()
					element_sets[set] = []
					
				elif set != '':

					if 'GEN=' in e:
						gen = e.replace('GEN=','')
						gen = gen.split(',')
						
						for i in range(int(gen[0]), int(gen[1])+1):
							element_sets[set].append(i)

					else:
						elements = e.split(',')
						for i in elements:
							element_sets[set].append(int(i))

			return element_sets

	def get_element_coordinates(self, element, model=1):
		'''
			Get the coordinates of a given element for a given model
			
			:param element: (``int``) - element number for which coordinates will be found
			:param model: (``int``) - the model from which coordinates will be extracted, defaults to 1 (first model)

			:return element_coords: (``list``) - list of lists [[x, y, z], [x, y, z]] for each node of the element
		'''
		
		element_coords = []
		nodes = self.get_element_nodes(element, model) #find the nodes for the given element
		
		for n in nodes:
			element_coords.append(self.get_node_coordinates(n, model))
		
		return element_coords

	def get_element_nodes(self, element, model=1):
		'''
			find the nodes of a given element
			
			:param element: (``int``) - element
			:param model: (``int``) - the model from which coordinates will be extracted, defaults to 1 (first model)

			:return (``list``) - [int, int] where the ints represent the elements node numbers
		'''
		first_node = None
		second_node = None
		elements = self.models[model]['*ELEMENT']

		for e in elements:
			e = e.replace(' ', '')
			e = e.split(',')
			
			if 'GEN' not in e[0]:
				if int(e[0]) == int(element) and len(e) >= 3:
					first_node = e[1]
					second_node = e[2]

		return [first_node, second_node]

	def get_node_coordinates(self, node, model=1):
		'''
			find the coordinates of a given node
			
			:param node: (``int\string``) - the node for which coordinates are required. If set to "all" all node coordinates are returned. If set to a int, coords for only that node are returned.
			:param model: (``int``) - the model from which coordinates will be extracted, defaults to 1 (first model)

			:return node_coordinates (``list\dict``) - [x, y, z] the coordinates of the node for a single nodes. For "all" nodes format is {n1: [x, y, z], n2: [x, y, z]} for all nodes in model
		'''

		node = str(node)
		node = node.strip()
		node_found = False
		
		if node.lower() == 'all':
			node_coordinates = {}
		else:
			node_coordinates = []
		
		if '*NODE' in self.models[model].keys():
			nodes = self.models[model]['*NODE']
			for n in nodes:
				n = n.replace(' ', '')
				n = n.split(',')
				
				if len(n) >= 4:
					coords = [float(n[1]), float(n[2]), float(n[3])]
					
					if node.lower() == 'all':
						node_coordinates[int(n[0])] = coords
					elif n[0].strip() == node:
						node_coordinates = coords
						node_found = True
						break

		return node_coordinates	

	def process_soil(self, model=1):
		'''
			extract the p-y curves for a given model
			self.p_y_curves is a dict that contains the p-y data
			keys are depths, values are dict with 'p' and 'y' keys
			
			:param model: (``int``) - the model from which coordinates will be extracted, defaults to 1 (first model)
		'''
		
		depth = None
		
		if '*P-Y' in self.models[model].keys():
			for idx, d in enumerate(self.models[model]['*P-Y']):

				if 'SET=' in d:
					pass
				elif 'NODE=' in d:
					#get elevation of node
					n = d.replace('NODE=', '')
					depth = self.get_node_coordinates(n)[0]
					self.p_y_curves[depth] = {'p': [], 'y': []}
					
				elif 'DEPTH=' in d:
					depth = float(d.replace('DEPTH=', ''))
					self.p_y_curves[depth] = {'p': [], 'y': []}
				
				else:
					if depth:
						if len(d.split(',')) == 2:
							d = d.split(',')
							self.p_y_curves[depth]['p'].append(float(d[0]))
							self.p_y_curves[depth]['y'].append(float(d[1]))

	def sum_all_soil_values(self):
		
		for depth in self.p_y_curves.keys():
			self.soil_sum += depth
			for p in self.p_y_curves[depth]["p"]:
				self.soil_sum += p
				
			for y in self.p_y_curves[depth]["y"]:
				self.soil_sum += y
						
	def find_casing_mass(self, model=1, verbose=False):
		'''
			Attempts to find the casing mass. Works by determining the lowest node coordinate in the model.
			Then it searches for a mass placed at that location. Assuming the casing/conductor are the lowest 
			elements in the model. This logic could probably be improved.
			
			:param model (``int``) - the model number for which the casing mass will be searched. Defaults to 1 (first model)
			:param verbose (``Bool``) - If True prints masses found to screen. Defaults to False
			
			:return casing_mass (``list``) - Nested list containing the node number and mass applied to lowest node in model [[n1, m1], [n2, m2]] node is int and mass is float, will be empty list if no appropriate mass is found. Note mass will be in default Deepriser unit e.g. slugs for imperial
		'''
		
		casing_mass = []
		
		if "*MASS" in self.models[model]:
			# Find the lowest Node coordinate in model
			lowest, lowest_node = self.find_lowest_nodes(model)

			# check *MASS to see if the lowest nodes have a mass assigned
			for m in self.models[model]['*MASS']:
				m = m.split(',')
				if int(m[0]) in lowest_node and 'MASS' in m[2]: #make sure type=MASS
					casing_mass.append([int(m[0]), float(m[1])])
		
		if verbose:
			print(f"The following mass values are found at the lowest point in the model (in format [node, mass]):")
			print(f"\t{casing_mass}")
			
		return casing_mass
	
	def find_lowest_nodes(self, model=1):
		'''
			This method finds the lowest node coordinate in the model
			
			:param model (``int``) - the model number for which the casing mass will be searched. Defaults to 1 (first model)
			
			:return lowest (``float``) - the lowest X coordinate in the model
			:return lowest_node (``list``) - a list of nodes (ints) whos X coordinate matches lowest
		'''

		coords = self.get_node_coordinates(node='all')
		
		lowest_node = []
		lowest = min([coords[n][0] for n in coords.keys()]) #lowest x coordinate in model
		
		#find node(s) that have the lowest x coordinate
		for node in coords.keys():
			if coords[node][0] == lowest:
				lowest_node.append(node)
		
		if self.verbose:
			print(f"\nLowest x coordinate identified as {lowest}{self.length_unit}")
			print("The following nodes are found at the lowest x coordinate:")
			print(f"\t{lowest_node}\n")
			
		return lowest, lowest_node

	def process_geometric_sets(self, model=1):
		geo_sets = {}
		
		if '*GEOMETRIC SETS' in self.models[model].keys():
			for s in self.models[model]['*GEOMETRIC SETS']:
				if 'SET=' in s:
					geo_sets[s.split('SET=')[1].strip().split(',')[0]] = []
				else:
					for ss in s.split(','):
						try:
							ss = float(ss)
						except:
							ss = None
						geo_sets[list(geo_sets.keys())[-1]].append(ss)

		#self.geo_columns = ['Set', 'EIyy', 'EIzz', 'GJ', 'EA', 'm', 'p', 'Di', 'Dd', 'Db', 'Do', 'Dc', 'Aux1', 'Aux2','Aux3','Aux4',]		

		#self.df_geo_sets = pd.DataFrame(self.geo_sets, columns =self.geo_columns)
		#self.df_geo_sets.set_index('Set', inplace=True)	
		
		return geo_sets
		
	def process_casing_conductor_program(self, model=1):
		'''
			This method attempts to find the conductor/casing elements in the model
			This is based on the PIP sets created by DR. It indentifies the elements based on sets with PIP Inner/Outer in the set name
			The output is a dict with start/end elevations and OD/ID for each set
			
			:param model (``int``) - the model number for which the casing mass will be searched. Defaults to 1 (first model)
			
			:return conductor_casing_program (``dict``) - dict, each key is a set name from the conductor/casing program, values are another dict with elvations and strucutral properties as keys
		'''
		
		conductor_casing_program = {}
		# Find PIP element sets
		pip_sets = []
		if "*ELEMENT SETS" in self.models[model]:
			for set in self.models[model]['*ELEMENT SETS']:
				if 'pip inner' in set.lower() or 'pip outer' in set.lower():
					pip_sets.append(set.replace('SET=', '').lstrip())
		
		# Get top/btm coord for each set
		elm_sets = self.process_element_sets(model)
		geo_sets = self.process_geometric_sets(model)
				
		for set in pip_sets:
			set_coords = []
			for elm in elm_sets[set]:
				c = self.get_element_coordinates(elm, model)
				if len(c[0]) > 0:
					set_coords.append(c[0][0])
				if len(c[1]) > 0:
					set_coords.append(c[1][0])
			# Had the comment out below list comprehension
			# If element nodes weren't in *NODE this would fail
			#set_coords = ([self.get_element_coordinates(elm, model)[x][0] for elm in elm_sets[set] for x in [0,1]])
			
			conductor_casing_program[set] = {'Start Elv': min(set_coords), 'End Elv': max(set_coords)}
			conductor_casing_program[set]['OD'] = geo_sets[set][9]
			conductor_casing_program[set]['ID'] = geo_sets[set][6]
		

		# Get OD/ID for each set
		if self.verbose:
			if len(list(conductor_casing_program.keys())) == 0:
				print("\nFailed to find element sets for conductor casing program")
			else:
				print("\nThe following element sets have been found in the conductor casing program")
				for set in conductor_casing_program.keys():
					print('\t' + set)
			
		return conductor_casing_program
		
	def get_tensioner_stiffness(self, model=1):
		self.tensioner_stiffness = None
		if "*TENSIONER" in self.models[model].keys():
			if 'STIFFNESS' in self.models[model]['*TENSIONER'][0]:
				self.tensioner_stiffness = float(self.models[model]['*TENSIONER'][0].split('STIFFNESS')[1].split(',')[0].replace('=', ''))

	def get_star_database(self, model=1):

		if '$POSTPROCESSING' in self.das_data.keys():
			if '*DATABASE' in self.das_data['$POSTPROCESSING'].keys():
				if "," in self.das_data['$POSTPROCESSING']['*DATABASE'][1]:
					self.database_start = float(self.das_data['$POSTPROCESSING']['*DATABASE'][1].split(',')[0])
	
	def find_output_files(self):
		
		for l in self.load_case_summary:
			name = self.load_case_summary[l]['Name']
			if len(list(self.models.keys())) == 1:
				output_file = f"{ os.path.dirname(os.path.abspath(self.das_file))}\\{name}\\{self.file_name.replace('.das', '.out')}"
				if os.path.isfile(output_file):
					self.output_files.append(output_file)
				
				
	def handle_errors(self):
		'''
			Print any errors to the screen after DasFile object is created
		'''
		if len(self.errors) > 0:
			if not self.print_name:
				print(self.das_file)
				
			print(f"{len(self.errors)} Errors Occurred!")
			for e in self.errors:
				print(e)

if __name__ == '__main__':
	
	'''
	Example Usage Below
	'''
	# Create DasFile instance, note full path the .das file required
	das = DasFile(r"V:\114-Projects\OP201177 Maersk - Developer Suriname Keskesi South 453m Riser Analysis\2.0 Drift-Off (440m WD)\28in_Casing_Sensitivity\New_Stack_Up\8.56ppg-DriftOff-UB Soil (440m) Base Case\analysis.das", verbose=True)
	#das.process_casing_conductor_program()
	#das.process_hydro_sets()
	das.find_output_files()
	print(das.output_files)