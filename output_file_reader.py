import os
import copy
import math

import matplotlib.pyplot as plt
import pandas as pd

from wood_dw.modelling_tools import structural_calcs

def create_output_file_dfs(output_files, csv=None):
	'''
		Merge all df_summary DataFrames into one single DataFrame
		
		:param output_files (``list``) - list of OutputFile objects
		:param csv (``string``) - path of csv file to write DataFrame too. Defaults to None, in which case no csv file is generated.
	'''
	df = pd.concat([x.df_summary for x in output_files]) 
	
	if csv:
		df.to_csv(csv)
		
	return df
	
class OutputFile():
	"""
	Author:
	-------------
		- Domhnall Morrisey 26/05/2021
		
	Prerequisites:
	-------------
		- Python > 3.9
		- pandas

	Limitations: 
	-------------
		- Limited error handling at the moment
		- Rotational offsets are not handled
		- Only regular wave data can be extracted

	Key Variables: 
	-------------
		- self.node_data (dict containing the coordinates (3 DOF) for each node)
		- self.heave (heave amplitude, obtained by running the get_vessel_heave method)
		
	TO DO: 
	-------------
		- Improve verbose and error handling
		- Extract constant boundary conditions in process_boundary_conditions method.
		- Add handling for irrelgular waves
	"""
	def __init__(self, output_file, solver='deepriser', verbose=False, print_name=True):
	
		'''
		:param das_file: (``string``) - full path of output file to be read
		:param solver: (``string``) - if the output file has been generated by "deepriser" or "flexcom". Not currently used.
		:param verbose (``boolean`` - optional): - Print internal messages if True (default value False).  
		:param print_name (``boolean`` - optional): - Print file name if True (default value True). Useful for tracking progress if reading multiple files
		'''	
		
		assert solver in ['deepriser', 'flexcom'], 'solver variable must be either "deepriser" or "flexcom"'
		assert os.path.isfile(output_file), f'Output file {output_file} does not exist!' #might remove this
		
		#setup instance variables
		self.output_file = output_file
		self.solver = solver
		self.verbose = verbose
		self.print_name = print_name
		if print_name:
			print(output_file)

		self.setup_variables()
		self.read_out_file()
		self.process_units()
		self.process_structural_details()
		self.process_nodal_data()
		self.process_element_data()
		self.process_element_properties()
		self.process_element_stress_properties()
		self.process_drag_data()
		self.process_environment_data()
		self.get_vessel_heave()
		self.process_offset()
		self.process_wave()
		self.gen_summary_df()

	def setup_variables(self):
		
		'''
			This method sets up default placeholder varaibles and sets them to None or empty lists and dicts.
			Detailed description of each var is given in the methods where they are fully defined.
		'''
		
		# read_out_file vars
		self.converged = None
		self.units = None 
		self.length_units = None
		self.out_data = {"headers": []}

		# NODAL COORDINATE DATA
		self.node_data = {}
		
		# *** ELEMENT PROPERTIES FOR STRESS CALCULATIONS *** 
		self.element_stress_properties = {}
		
		# *** ELEMENT PROPERTIES ***
		self.element_properties = {}
		
		# *** DRAG AND BOUANCY DATA ***
		self.drag_data = {}
		
		#process_environment_data vars
		self.water_depth = None
		
		# process_offset vars
		self.offsets = None
		self.offset_mag = None
		self.offset_perc_wd = None

		# boundary conditions
		self.no_constant_bcs = None # Number of constant BCs
		self.no_vessel_bcs = None # Number of vessel BCs
		self.boundary_conditions = {'Constant': {}, 'Vessel': {}}
		
		self.heave = None
		self.stats_of_motion = {}
		self.vessel_ref_point = None
		
		#wave
		self.wave = {'wave type': None, 'wave range': None, 'wave period': None, 'wave direction': None}
		
		# PIP SECTIONS
		self.pip_sections = []
		#Structural details
		'''
		Need to add method to grab these
		'''
		self.structural_details = {}
		
	def read_out_file(self):
		
		'''
			This method reads and parses the output file data.
			The data is parsed into a dict called self.out_data. The keys for the dict are the *** headers in the output file.
			For example *** ELEMENT PROPERTIES *** will be present as key without the *** e.g. "ELEMENT PROPERTIES": []
			The values are a list conatining each line in a given section of the output file.
			Blank lines are ignored.
			
			The method also checks for convergance will reading in each line. 
			If "successful deepriser/flexcom analysis" is found in the line (.lower()) then conveged
			
			:created var self.out_data (``dict``) - see detailed description above. contains all output file data
			:created var self.converged (``bool``) - wether the analysis converged or not. See criteria above.
		'''
		
		#section = None
		# #######################
		key = 'headers'
		f = open(self.output_file, 'r')
		
		while True:
			line = f.readline()

			if not line:
				break
				
			if f'successful {self.solver} analysis' in line.lower():
				self.converged = True
				
			if 'Error: Solution has failed to converge.' in line:
				self.converged = False
			
			if 'Error: The restart file for this analysis does not exist.' in line:
				self.restart = False
				self.converged = False
			
			if 'No database files exist for opening.' in line:
				self.converged = False
				
			if 'dongle' in line:
				self.converged = False
				

			line = 	line.replace('\n', '')
			if len(line) > 0:
				if ' *** ' in line and 'Articulation Element' not in line:
					key = line.replace('***', '').strip()
					self.out_data[key] = []
				elif len(line.strip()) > 0:
					self.out_data[key].append(line)
		f.close()
		
		if self.verbose:
			print(f"\n Read {self.output_file} succesfully")
			if not self.converged:
				self.show_error(f"Output file {self.output_file} did not converge")

	def process_units(self):
		
		'''
			This method checks what units the analysis is performed in.
		'''
	
		if 'UNIT SYSTEM' in self.out_data.keys():
			for l in self.out_data['UNIT SYSTEM']:
				if 'Imperial' in l:
					self.units = 'Imperial'
					self.length_units = 'ft'
				elif 'Metric' in l:
					self.units = 'Metric'
					self.length_units = 'm'

	def process_structural_details(self):
		if "STRUCTURAL DISCRETISATION DETAILS" in self.out_data.keys():
			for d in self.out_data["STRUCTURAL DISCRETISATION DETAILS"]:
				if "No. of Pipe-in-Pipe Connections" in d:
					self.structural_details["No. of Pipe-in-Pipe Connections"] = int(d.split(":")[1])
					
	def process_environment_data(self):
		'''
			This method finds the water depth of the analysis
			
			:var created self.water_depth (``float``) - the water depth.
		'''
		if 'OCEAN ENVIRONMENT DATA' in self.out_data.keys():
			for d in self.out_data['OCEAN ENVIRONMENT DATA']:
				if '.' in d:
					self.water_depth = float(d.split()[0])

	def process_nodal_data(self):
		'''
			This method extract the nodal cooridinates into a dict. Data is extracted from *** NODAL DATA ***
			
			: var updated self.node_data (``dict``) - keys are node numbers, values are another dict with the cooridinates for each DOF.
						This is in the form { n1: {'DOF 1': x1, 'DOF 2': y1, 'DOF 3': z1}, n2: {'DOF 1': x1 .....}}
						Node numbers are stored as ints, coordinates are stored as floats.
		'''
		
		if "NODAL DATA" in self.out_data.keys():	
			for e in self.out_data['NODAL DATA']:
				if 'Node No.' not in e:
					e = e.split()
			
					if len(e) == 4:
						self.node_data[int(e[0])] = {'DOF 1': float(e[1]), 'DOF 2': float(e[2]), 'DOF 3': float(e[3])}	

					if len(e) == 5:
						self.node_data[int(e[0])] = {'DOF 1': float(e[1]), 'DOF 2': float(e[2]), 'DOF 3': float(e[3]), 'Contact Diameter': float(e[4])}	

	def process_element_data(self):
		self.element_data = {}
		
		if "ELEMENT DATA" in self.out_data.keys():
			for e in self.out_data["ELEMENT DATA"]:
				e = e.split()
				
				if len(e) == 12 or len(e) == 9:
					if "Element" not in e:
						self.element_data[int(e[0])] = {"Start Node": int(e[1]), "End Node": int(e[2])}

	def process_element_stress_properties(self):

		if "ELEMENT PROPERTIES FOR STRESS CALCULATIONS" in self.out_data.keys():
			if self.verbose:
				print("Processing ELEMENT PROPERTIES FOR STRESS CALCULATIONS")
				
			for e in self.out_data["ELEMENT PROPERTIES FOR STRESS CALCULATIONS"]:
				if "***" not in e and "Element" not in e and "----" not in e and "Number" not in e:
					e = e.split()
					if int(e[0]) in self.element_data.keys():
						self.element_stress_properties[int(e[0])] = {"Effective Do": float(e[1]), "Effective Di": float(e[2])}				
		else:
			if self.verbose:
				print("ELEMENT PROPERTIES FOR STRESS CALCULATIONS not found in output file")		
		
	def process_element_properties(self):
	
		if "ELEMENT PROPERTIES" in self.out_data.keys():
			if self.verbose:
				print("Processing ELEMENT PROPERTIES")
				
			for e in self.out_data["ELEMENT PROPERTIES"]:
				if "***" not in e and "Element" not in e and "----" not in e and "Inertia" not in e:
					e = e.split()
					if int(e[0]) in self.element_data.keys():
						self.element_properties[int(e[0])] = {"EI-yy": float(e[1])}				
		else:
			if self.verbose:
				print("ELEMENT PROPERTIES not found in output file")
	
	def process_drag_data(self):

		if "DRAG AND BUOYANCY DATA" in self.out_data.keys():
			if self.verbose:
				print("Processing DRAG AND BUOYANCY DATA")
				
			for e in self.out_data["DRAG AND BUOYANCY DATA"]:
				if "***" not in e and "Element" not in e and "----" not in e and "Diameter" not in e:
					e = e.split()
					if int(e[0]) in self.element_data.keys():
						self.drag_data[int(e[0])] = {"Internal Diameter": float(e[1])}				
		else:
			if self.verbose:
				print("DRAG AND BUOYANCY DATA not found in output file")
				
	def get_element_coords(self, element, type='static'):
		'''
		Return list, [Start_coord, center_coord, end_coord]
		'''
		element_coords = [None, None, None]
		
		# element = str(element).strip()
		element = int(element)
		
		if type == 'static':
			# sfd
			try:
				element_coords[0] = self.node_data[self.element_data[element]['Start Node']]['DOF 1']
				element_coords[2] = self.node_data[self.element_data[element]['End Node']]['DOF 1']
			
				element_coords[1] = (element_coords[0] + element_coords[2])/2
			except:
				print(self.node_data)
				print(f'could not process element {element} coordinates')
				asds
		elif type == 'kinematic':
			try:
				element_coords[0] = self.kinematic_variables[self.element_data[element]['Start Node']]['DOF 1']['Pos']
				element_coords[2] = self.kinematic_variables[self.element_data[element]['End Node']]['DOF 1']['Pos']
				
				element_coords[1] = (element_coords[0] + element_coords[2])/2
			except:
				print(f'could not process element {element} coordinates')

		else:
			print("Can't Process Element Coordinates, incorrect type passed to function")
		return element_coords

	def process_element_set(self, start_elm, end_elm):
		'''
			Return the following info for each element
				element number
				start node
				end node
				start elevation
				end elevation
				OD
				ID
		'''
		element_set_data = []
		
		for elm in range(start_elm, end_elm+1):
			coords = self.get_element_coords(elm)
			di = self.element_stress_properties[elm]["Effective Di"]
			do = self.element_stress_properties[elm]["Effective Do"]
			
			element_set_data.append([elm, self.element_data[elm]["Start Node"], self.element_data[elm]["End Node"],
									min(coords), max(coords), do, di])
		
		return element_set_data
		
	def process_offset(self):
		'''
			This method extracts the vessel offest from *** OUTPUT OF VESSEL MOTION DATA ***
			Note rotational offsets are not handled.
			
			: var created self.offsets (``list``) - list of floats of the translational offests [Tx, Ty, Tz]
			: var created self.offset_mag (``float``) - total offset in length units e.g. ft or m
			: var created self.offset_perc_wd (``float``) - total offset in %WD
		'''
		if 'OUTPUT OF VESSEL MOTION DATA' in self.out_data.keys():
			
			for d in self.out_data['OUTPUT OF VESSEL MOTION DATA']:

				if 'Vessel Offset (Global Coordinates):' in d:
					offset_data = d.split(':')[1].split()

					if len(offset_data) == 6: # flexcom format (includes ft/m in this line)
						self.offsets = [float(offset_data[i]) for i in [0, 2, 4]]
						self.offset_mag = (self.offsets[1] ** 2 + self.offsets[2] ** 2) ** 0.5
						self.offset_perc_wd = round(self.offset_mag / self.water_depth,2)
						
					elif len(offset_data) == 3: #deepriser format
						self.offsets = [float(offset_data[i]) for i in [0, 1, 2]]
						self.offset_mag = (self.offsets[1] ** 2 + self.offsets[2] ** 2) ** 0.5
						self.offset_perc_wd = round(self.offset_mag / self.water_depth,2)			
			
			if not self.offset_perc_wd:
				self.offset_perc_wd = 0 #if we have no errors and no offset is found, then we can assume no offset was requested
				
		if self.verbose:
			if not self.offset_perc_wd:
				print('Offsets were not correctly read')
			else:
				print('Offsets succesfully read')

	def process_analysis_times(self):
		'''
			This method extracts the analysis start time and end time.
		'''
		self.start_time = None
		self.finish_time = None
		
		if "TIME VARIABLES" in self.out_data.keys():
			
			for d in self.out_data['TIME VARIABLES']:
				if 'Analysis Start Time' in d:
					self.start_time = d.split(':')[-1].split()[0]
				if 'Analysis Finish Time' in d:
					self.finish_time = d.split(':')[-1].split()[0]

	def process_boundary_conditions(self, verbose=False):
		
		'''
			This method extracts the boundary conditions applied to the analaysis.
			At present only vessel boundary conditions are considered!
			
			:param verbose (``bool``) - Print internal messages if True (default value False).
			
			:var created self.boundary_conditions (``dict``) - dict with keys 'Constant' and 'Vessel' for each BC type.
																values for these are another dict in the following format
																	{node: [1, 2, 3 ....]} where node is a int node number, and the list represents the DOFs for which a BC has been applied to that node.
		'''

		if 'BOUNDARY CONDITION INPUT DATA' in self.out_data.keys():
		
			for line_idx, d in enumerate(self.out_data['BOUNDARY CONDITION INPUT DATA']):
				if 'No. of Constant Specified Displacements' in d:
					self.no_constant_bcs = int(d.split(':')[1])
				if 'No. of Attached Vessel Displacements' in d:
					self.no_vessel_bcs = int(d.split(':')[1])
				
				if 'DISPLACEMENTS SPECIFIED FROM MOTION OF ATTACHED FLOATING VESSEL' in d:
					#extract the vessel BCs from self.out_data
					vessel_bcs = self.out_data['BOUNDARY CONDITION INPUT DATA'][line_idx+3: line_idx+3+self.no_vessel_bcs]

					for bc in vessel_bcs: #loop over each vessel BC
						bc = bc.split()
						node = int(bc[0]) #the node number
						
						if node not in self.boundary_conditions['Vessel'].keys():
							self.boundary_conditions['Vessel'][node] = [] #list of DOFs for which a BC is applied to this node
						
						self.boundary_conditions['Vessel'][node].append(int(bc[1]))# append the DOF
		
		if verbose:
			print(f"{self.no_vessel_bcs} Vessel Boundary Conditions Extracted")
			
			if not self.no_vessel_bcs:
				self.show_error("Could not Process Vessel Boundary Conditions")

	def process_statistics_of_motion(self, verbose=False):
	
		'''
			This method extracts the statics of motion from the output file. Min and max translations/rotations for each node are extracted.
			
			:param verbose (``bool``) - Print internal messages if True (default value False).
			:var created self.stats_of_motion (``dict``) - dict in format {N1: {1: [Xmin, Xmax], 2: [Ymin Ymax], etc...}, N2:{}, etc....}
															N1, N2 are node numbers, 1, 2 are DOFs 1 and 2 (up to DOF 6 is included)
															Xmin, Xmax are min and max displacments (translations in X/DOF1 in this case).
		'''

		
		if 'STATISTICS OF MOTION' in self.out_data.keys():
			for d in self.out_data['STATISTICS OF MOTION']:
				
				offset = 0
				if len(d.split()) == 6 or len(d.split()) == 5:
					if 'Node' not in d:
						d = d.split()
						if len(d) == 6:
							node = int(d[0])
							offset = 1
							self.stats_of_motion[node] = {}
							
						dof = d[0+offset]
						min = float(d[1+offset])
						max = float(d[2+offset])
						
						self.stats_of_motion[node][f'DOF {dof}'] = {'Min': min, 'Max': max}
		if verbose:
			if self.stats_of_motion == {}:
				print("Statistics of Motion not Found\n")
			else:
				print(f"Statistics of Motion found for {len(self.stats_of_motion.keys())} Nodes")


	def get_vessel_ref_point(self, verbose=False):
		'''
			This method extracts the vessel reference point
			
			:param verbose (``bool``) - Print internal messages if True (default value False).
			:var created self.vessel_ref_point (``list``) - [x, y, z] cooridinates of the vessel ref point (as floats)
		'''
		
		if 'OUTPUT OF VESSEL MOTION DATA' in self.out_data.keys():
		
			for d in self.out_data['OUTPUT OF VESSEL MOTION DATA']:
				if 'Initial Coordinates of Vessel Reference Point:' in d:
				
					d = d.split(':')[-1].split()
					
					self.vessel_ref_point = [float(a) for a in d]
					break
		
		if verbose:
			if not self.vessel_ref_point:
				print("Could not find Vessel Reference Point")
			else:
				print(f"Vessel reference point identifided as {self.vessel_ref_point}")
			
	def get_vessel_heave(self, verbose=False):
		
		'''
			This method attempts to extract the vessel heave.
			It checks for any nodes with vessel BCs. If there are multiple nodes, the one closest to the vessel reference point is taken.
			The statistics of motion section contains the max and min X coordinate for the node throughout the analysis. The delta between those is approx. the vessel heave.
			
			:param verbose (``bool``) - Print internal messages if True (default value False).
			: var created self.heave (``float``) - float value of the heave amplitude.
		'''
		self.process_boundary_conditions(verbose=verbose)
		self.process_statistics_of_motion(verbose=verbose)
		self.get_vessel_ref_point(verbose=verbose)
		
		#find nearest BC to vessel reference point
		nodes= []
		distance_to_ref=[]
		#print(self.boundary_conditions)
		#print(self.stats_of_motion)
		if len(self.boundary_conditions['Vessel']) > 0:
			
			for node in self.boundary_conditions['Vessel'].keys():


				if 1 in self.boundary_conditions['Vessel'][node]: #if dof 1 is in the BC
					
					if node in self.stats_of_motion.keys():
					
						if self.vessel_ref_point == None:
							minimum = self.stats_of_motion[node]['DOF 1']['Min']
							maximum = self.stats_of_motion[node]['DOF 1']['Max']
							
							self.heave = maximum-minimum
							break
							
						else: #calc distance to vessel ref point
							nodes.append(node)
							x = (self.node_data[node]['DOF 1'] - self.vessel_ref_point[0])**2
							y = (self.node_data[node]['DOF 2'] - self.vessel_ref_point[1])**2
							z = (self.node_data[node]['DOF 3'] - self.vessel_ref_point[2])**2
							
							distance_to_ref.append(math.sqrt(x+y+z))

		# get closest node to vessel ref
		if self.vessel_ref_point != None and len(distance_to_ref) > 0:

			node = nodes[distance_to_ref.index(min(distance_to_ref))]
			minimum = self.stats_of_motion[node]['DOF 1']['Min']
			maximum = self.stats_of_motion[node]['DOF 1']['Max']
			
			self.heave = round(maximum-minimum,2) #note calculated heave is amplitude
			
		if verbose:
			if not self.heave:
				self.show_error('Could not process vessel heave')
			else:
				print(f"Vessel heave identifided as {self.heave}")

	def process_wave(self, verbose=False):
		'''
			This method extracts the wave data to a dict (self.wave).
			NOTE!! Only regular wave is handled at the moment!!
			
			:param verbose (``bool``) - Print internal messages if True (default value False).
			: var created self.wave (``dict``) - dict of wave parameter keys and float values. e.g. {'Wave Period': 10, 'Wave Direction: -150}
		'''
		if 'SPECTRUM DISCRETISATION DATA' in self.out_data.keys():
			# Determine the wave type used
			for line in self.out_data['SPECTRUM DISCRETISATION DATA']:
				if 'regular' in line.lower():
					self.wave['wave type'] = 'regular'
			
			if self.wave['wave type']:
				wave_line = self.out_data['SPECTRUM DISCRETISATION DATA'][-1].split() #the wave data should be the last line
			
				if self.wave['wave type'] == 'regular':
					params = ['wave no.', 'wave range', 'wave period', 'wave direction']
					
					for idx, p in enumerate(params):
						if idx > 0: #ignore wave no.
							self.wave[p] = float(wave_line[idx])
							if p == 'wave range':
								self.wave[p] = self.wave[p]*2 #convert from amplitude to range
		
		if self.verbose:
			if not self.wave['wave type']:
				print('\n No wave found')
			elif self.wave['wave type'] == 'regular':
				print(f"Regular wave run with {self.wave['wave range']}{self.length_units} range")

	def gen_summary_df(self):
		'''
			This method combines various variables throughout the class instance into a pandas DataFrame.
		'''
		
		summary_dict = copy.deepcopy(self.wave)
		summary_dict['heave'] = self.heave
		summary_dict['offset %wd'] = self.offset_perc_wd
		summary_dict['converged'] = self.converged
		
		for key in summary_dict.keys():
			summary_dict[key] = [summary_dict[key]] #make each value in the dict a list (for conversino to DataFrame)
		
		self.df_summary = pd.DataFrame.from_dict(summary_dict, orient='columns')

	def get_tension_values(self, element, position):
		assert position in ['Start', 'Midpoint', 'End'], 'position must be Start, Midpoint or End'
		
		tension_data = {'Min': None, 'Max': None, 'Mean': None}
		found_elm = False
		if 'STATISTICS OF ELEMENT RESTORING FORCES' in self.out_data.keys():
			for line in self.out_data['STATISTICS OF ELEMENT RESTORING FORCES']:
				if 'Location' not in line:
					line = line.split()
					if len(line) == 7 and int(line[0]) == int(element):
						found_elm = True
						
					if found_elm:
						if position in line:
							tension_data['Min'] = float(line[-4])
							tension_data['Max'] = float(line[-3])
							tension_data['Mean'] = float(line[-2])
							break

		return tension_data

	def get_pip_sections(self):
		if "PIPE-IN-PIPE CONNECTIONS DATA" in self.out_data.keys():
			for line in self.out_data["PIPE-IN-PIPE CONNECTIONS DATA"]:
				if "fixed" in line.lower() or "sliding" in line.lower():
					line = line.split()
					n1 = int(line[2])
					n2 = int(line[3])
					if "curve" not in line[4].lower():
						perpendicular_stiffness = float(line[4])
					else:
						perpendicular_stiffness = 0.0
						
					self.pip_sections.append([n1, n2, self.node_data[n1]['DOF 1'], self.node_data[n1]['DOF 1'], perpendicular_stiffness])
		
		self.df_pip_sections = pd.DataFrame(self.pip_sections, columns=['Node 1', 'Node 2', "Node 1 Elevation", "Node 2 Elevation", "Perpendicular Stiffness"])
		self.df_pip_sections.sort_values(by=['Node 1 Elevation'], inplace=True)
			
	def show_error(self, msg):
		print(f"**** Error!\n\t {msg}")
		
def check_output_files(path, solver='deepriser', ignore_ss=True):
	
	output_files = {}
	
	counter = 1
	for root, dirs, files in os.walk(path):
		process_root = True
		if ignore_ss:
			if root.lower() == 'ss' or root.lower() == '_ss':
				process_root = False
			
		if process_root:
		
			for file in files:
				if file.endswith(".out"):
					
					o = OutputFile(f'{root}\\{file}', solver)
					o.process_offset()
					#o.process_current()
					o.process_analysis_times()
					#o.process_boundary_conditions()
					o.get_vessel_heave()
					
					#add pip connections
					pip = 0

					if 'No. of Pipe-in-Pipe Connections' in o.structural_details.keys():
						pip = o.structural_details['No. of Pipe-in-Pipe Connections']
							
						
					# output_files[counter] = {'Root': root, 'File': file, 'Converged': o.converged,
											# 'Offset %WD': o.offset_perc_wd, 'Current Avg': o.mean_current_vel,
											# 'Start Time': o.start_time, 'Finish Time': o.finish_time,
											# 'No Constant BCs': o.no_constant_bcs,
											# 'No Vessel BCs': o.no_vessel_bcs,
											# 'Vessel Heave': o.heave,
											# 'No of PIP Connections': pip}


					output_files[counter] = {'Root': root, 'File': file, 'Converged': o.converged,
											# 'Offset %WD': o.offset_perc_wd, 'Current Avg': o.mean_current_vel,
											'Start Time': o.start_time, 'Finish Time': o.finish_time,
											'No Constant BCs': o.no_constant_bcs,
											'No Vessel BCs': o.no_vessel_bcs,
											'Vessel Heave': o.heave,
											'No of PIP Connections': pip,
											}
											
					print(f'{root}\\{file} : {o.converged}')
					df = pd.DataFrame.from_dict(output_files, orient='index')
					print(df.tail())
					counter += 1
	return df
	
def check_lmrp_overpull(path, lmrp_elm, solver='deepriser', ignore_ss=True):
		
	output_files = {}
	min_tensions = []
	max_tensions = []
	mean_tensions = []
	variations = []
	index = []
	
	counter = 1
	for root, dirs, files in os.walk(path):
		process_root = True
		if ignore_ss:
			if root.lower() == 'ss' or root.lower() == '_ss':
				process_root = False
			
		if process_root:
		
			for file in files:
				if file.endswith(".out"):
					
					o = OutputFile(f'{root}\\{file}', solver)
					tension_data = o.get_tension_values(lmrp_elm, 'Start')
					min_tensions.append(tension_data['Min'])
					max_tensions.append(tension_data['Max'])
					mean_tensions.append(tension_data['Mean'])
					variations.append(tension_data['Max'] - tension_data['Min'])
					index.append(counter)
					counter += 1
	
	plt.scatter(index, min_tensions, label='min', color='blue')
	plt.scatter(index, max_tensions, label='max', color='red')
	plt.scatter(index, mean_tensions, label='mean', color='green')
	#plt.scatter(index, variations, label='variation', color='black')
	
	plt.legend()
	plt.grid()
	plt.show()
	
if __name__ == '__main__':
		
	#check_lmrp_overpull(r'\\r-ana-iegwmcs-5\E\114-Projects\OP211898 Karoon\02 Weakpoint\01 7-PRA-2-SPS\02 Dynamic\200kips', 98)
	
	# o = OutputFile(r"T:\114-Projects\OP221288 - Maersk Drilling - Voyager Suriname Zanderij South-1 2,273m Riser Analysis\01 DPX\04 BOP Deployment\BOP Deployment - Dynamic\Modified Das\MPM Hs 1.0m Tp10s 10pc NE Current\Stage 1\analysis.out")
	# o.get_pip_sections()
	
	check_output_files(r"Q:\114-Projects\OP213512 Stena Spey Riser Analysis 80m\2.0 Detailed Tensioner Setup\Dynamic Calibration")